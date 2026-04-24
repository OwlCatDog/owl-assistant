using System;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Controls.Notifications;
using Avalonia.Markup.Xaml;
using Flurl.Http;
using OwlAssistant.Resources;
using OwlAssistant.ViewModels;
using OwlAssistant.Views;
using Serilog;
using Serilog.Events;

namespace OwlAssistant;

public partial class App : Application
{
    public override void Initialize()
    {
        AvaloniaXamlLoader.Load(this);
    }

    public override async void OnFrameworkInitializationCompleted()
    {
        Log.Logger = new LoggerConfiguration()
            .MinimumLevel.Debug()
            .MinimumLevel.Override("Microsoft", LogEventLevel.Information)
            .Enrich.FromLogContext()
            .WriteTo.Console()
            .WriteTo.Debug()
            .CreateLogger();

        _ = Task.Run(async () =>
        {
            try
            {
                // check environment
                // throw new Exception();
                await GlobalCfg.ThermalOnline
                    .WithTimeout(TimeSpan.FromMilliseconds(500))
                    .PostJsonAsync(new { })
                    .ReceiveString();
            }
            catch (Exception)
            {
                // use global
                Log.Error("Using fallback url");
                GlobalCfg.ApiBaseUrl = $"(SECRET)";
                GlobalCfg.UseFrp = true;
            }
        });
        Thread.Sleep(600);

        FlurlHttp.Clients.WithDefaults(builder =>
            builder.BeforeCall(call =>
                {
                    // if (call.Request.Url.ToUri().Host.Contains("mrowl.xyz"))
                    // {
                    if (!GlobalCfg.UseFrp)return;
                        var timeWindow = DateTimeOffset.Now.ToUnixTimeSeconds() / 120;
                        var rawStr = $"{timeWindow}:{GlobalCfg.Salt}";
                        var bytes = Encoding.UTF8.GetBytes(rawStr);
                        var hashBytes = SHA256.HashData(bytes);
                        var result = Convert.ToHexString(hashBytes).ToLower();
                        call.Client.WithHeader("owl-auth-token", result);
                    // }
                })
                .ConfigureInnerHandler(handler =>
                {
                    if (OperatingSystem.IsBrowser()) return;
                    handler.ServerCertificateCustomValidationCallback = (message, cert, chain, errors) => true;
                })
        );


        AppDomain.CurrentDomain.UnhandledException += (s, e) =>
            Log.Write(LogEventLevel.Error, (Exception)e.ExceptionObject, "Unhandled exception");
        TaskScheduler.UnobservedTaskException +=
            (s, e) => Log.Write(LogEventLevel.Error, e.Exception, "Unobserved task exception");


        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            desktop.MainWindow = new MainWindow
            {
                DataContext = new MainWindowViewModel()
            };

            GlobalVar.Manager = new WindowNotificationManager(desktop.MainWindow);
            GlobalVar.TopLevel = desktop.MainWindow;
        }
        else if (ApplicationLifetime is ISingleViewApplicationLifetime singleViewPlatform)
        {
            singleViewPlatform.MainView = new MainView
            {
                DataContext = new MainWindowViewModel()
            };
            GlobalVar.Manager = new WindowNotificationManager(TopLevel.GetTopLevel(singleViewPlatform.MainView));
            GlobalVar.TopLevel = TopLevel.GetTopLevel(singleViewPlatform.MainView);
        }

        base.OnFrameworkInitializationCompleted();
    }
}
