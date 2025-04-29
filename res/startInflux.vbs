Set WshShell = CreateObject("WScript.Shell") 
WshShell.Run chr(34) & "C:\Program Files\InfluxData\influxdb2_windows_amd64\influxd.exe" & Chr(34) & " --bolt-path=D:\.influxdbv2\influxd.bolt --engine-path=D:\.influxdbv2\engine", 0
Set WshShell = Nothing