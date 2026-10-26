$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$projectDir = Split-Path -Parent $PSScriptRoot
$speechPath = Join-Path $projectDir 'artifacts\test-speech.wav'
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $englishVoice = $synth.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'en-*' } | Select-Object -First 1
    if ($englishVoice) { $synth.SelectVoice($englishVoice.VoiceInfo.Name) }
    $synth.SetOutputToWaveFile($speechPath)
    $synth.Speak('Hello world. This is a real time translation test. We can read subtitles while the speakers are muted.')
} finally {
    $synth.Dispose()
}
Write-Output $speechPath
