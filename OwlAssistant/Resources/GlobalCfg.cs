namespace OwlAssistant.Resources;

public class GlobalCfg
{
    public static string Salt  { get; set; } = "（SECRET）";

    public static bool UseFrp { get; set; } = false;
    
    private static string _apiBaseUrl = "http://scan.mrowl.xyz:8080/api/v1/";
    
    public static string ApiBaseUrl
    {
        get => _apiBaseUrl.EndsWith("/") ? _apiBaseUrl : $"{_apiBaseUrl}/";
        set => _apiBaseUrl = value;
    }
    
    public static string SysCompleteInfo => $"{ApiBaseUrl}system/summary";
    
    public static string RawInfo => $"{ApiBaseUrl}system/raw";
    
    public static string ThermalOnline => $"{ApiBaseUrl}printer/online";
    
    public static string ThermalSysPrint => $"{ApiBaseUrl}printer/system-ticket";
    
    public static string ThermalPrint => $"{ApiBaseUrl}printer/print";
    
    public static string SensorData => $"{ApiBaseUrl}sensors/latest";
    
    public static string SensorDataRange => $"{ApiBaseUrl}sensors/history";
    
    public static int RawInfoInterval => 5;

    public static int DefaultRequestTimeout => 10;

    public static string InsideSensorMac => "A4:C1:38:CF:B0:D6";
    
    public static string OutsideSensorMac => "A4:C1:38:D5:05:79";
    
    public static string DarkinName => "darkin";
}
