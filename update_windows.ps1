# tvlistesi kanal listesini Windows'ta saatlik otomatik gunceller.
# Calistirma: powershell -ExecutionPolicy Bypass -File .\update_windows.ps1
$hata = $null
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $python) { throw "Python bulunamadi." }

$klasor = Split-Path -Parent $MyInvocation.MyCommand.Path
$arguman = "`"$(Join-Path $klasor 'generate.py')`""

$action = New-ScheduledTaskAction -Execute $python -Argument $arguman -WorkingDirectory $klasor
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
  -RepetitionInterval (New-TimeSpan -Hours 1) `
  -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName "tvlistesi-kanal-guncelleme" `
  -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Host "Gorev olusturuldu: tvlistesi-kanal-guncelleme (saatte bir)"
Write-Host "Kaldirmak icin: Unregister-ScheduledTask -TaskName 'tvlistesi-kanal-guncelleme' -Confirm:`$false"
