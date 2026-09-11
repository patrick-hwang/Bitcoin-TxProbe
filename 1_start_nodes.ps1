# ==========================================
# 1. Start Tor
# ==========================================
Write-Host "    Starting Tor daemon..." -ForegroundColor Cyan
# Change path to your tor.exe location
$torProgramPath = "C:\Users\Dell\tor\tor\tor.exe"
$torConfigurationPath = "D:\MAIN QUEST 03 - Bitcoin\Bitcoin-TxProbe\torrc"
$torLogPath = "$env:TEMP\tor_bootstrap.log"
$torTitle = "Tor"

if (-not (Test-Path $torProgramPath)) {
    Write-Host "[!] tor.exe not found at $torProgramPath" -ForegroundColor Red
    return
}

if (-not (Test-Path $torConfigurationPath)) {
    Write-Host "[!] torrc not found at $torConfigurationPath" -ForegroundColor Red
    return
}

if (Test-Path $torLogPath) {
    Write-Host "Remove existed tor log $torLogPath"
    Remove-Item $torLogPath -Force
}

Start-Process -FilePath $torProgramPath -ArgumentList "-f", "`"$torConfigurationPath`"", "--Log", "`"notice file $torLogPath`"" -WindowStyle Normal

cmd.exe /c start "`"$torTitle`"" /min "`"$torPath`"" -f "`"$torrcPath`""

# Wait for Tor to bootstrap 100%
Write-Host "    Waiting for Tor to bootstrap..." -NoNewline -ForegroundColor Gray

while ($true) {
    if (Test-Path $torLogPath) {
        $content = Get-Content -Path $torLogPath -ErrorAction SilentlyContinue | Out-String
        if ($content -match "Bootstrapped 100%") {
            break
        }
    }
    Write-Host "." -NoNewline -ForegroundColor Gray
    $torProcess = Get-Process -Name "tor"
    if (-not ($torProcess)) {
        Write-Host "[!] Tor is terminated." -ForegroundColor Red
        return
    }
    Start-Sleep -Seconds 2
}
Write-Host ""

Write-Host " Ready!" -ForegroundColor Green

# ==========================================
# 2. Start 5 Windows bitcoind instances
# ==========================================
Write-Host "[*] Starting Windows Bitcoin Nodes..." -ForegroundColor Cyan

$winBitcoind = "C:\Program Files\Bitcoin\daemon\bitcoind.exe"

# Define node configs/directories: @("datadir", "conf")
$winNodes = @(
    @("C:\Users\Dell\AppData\Local\bitcoin-testnet4-1", "C:\Users\Dell\AppData\Local\bitcoin-testnet4-1\bitcoin.conf"),
    @("C:\Users\Dell\AppData\Local\bitcoin-testnet4-2", "C:\Users\Dell\AppData\Local\bitcoin-testnet4-2\bitcoin.conf"),
    @("C:\Users\Dell\AppData\Local\bitcoin-testnet4-3", "C:\Users\Dell\AppData\Local\bitcoin-testnet4-3\bitcoin.conf"),
    @("C:\Users\Dell\AppData\Local\bitcoin-testnet4-4", "C:\Users\Dell\AppData\Local\bitcoin-testnet4-4\bitcoin.conf"),
    @("C:\Users\Dell\AppData\Local\bitcoin-testnet4-5", "C:\Users\Dell\AppData\Local\bitcoin-testnet4-5\bitcoin.conf")
)

$num = 0
foreach ($node in $winNodes) {
    $dir  = $node[0]
    $conf = $node[1]
    $num++
    $nodeTitle = "Bitcoind-$num"
    Write-Host "    Launching Windows node at $dir`: $nodeTitle"
    cmd.exe /c start "`"$nodeTitle`"" /min $winBitcoind -datadir="`"$dir`"" -conf="`"$conf`""
}

# ==========================================
# 3. Start 2 WSL bitcoind instances
# ==========================================
Write-Host "[*] Starting WSL Bitcoin Nodes..." -ForegroundColor Cyan

# Linux paths inside your WSL environment
$wslNodes = @(
    @("/mnt/c/Users/Dell/AppData/Local/bitcoin-testnet4-0", "/mnt/c/Users/Dell/AppData/Local/bitcoin-testnet4-0/bitcoin.conf"),
    @("/mnt/c/Users/Dell/AppData/Local/bitcoin-testnet4-6", "/mnt/c/Users/Dell/AppData/Local/bitcoin-testnet4-6/bitcoin.conf")
)

# Linux path to your custom compiled bitcoind
$wslBitcoind = "/mnt/d/MAIN QUEST 03 - Bitcoin/Bitcoin-TxProbe/build/bin/bitcoind"

$num = 0
foreach ($node in $wslNodes) {
    $dir  = $node[0]
    $conf = $node[1]
    $nodeTitle = "Bitcoind-$num"
    $num += 6
    $bashCmd = "printf '\033]0;$nodeTitle\007'; '$wslBitcoind' -datadir='$dir' -conf='$conf'"
    Write-Host "    Launching WSL node at $dir`: $nodeTitle"
    cmd.exe /c start /min wsl.exe -u root bash -c "$bashCmd"
}

Write-Host "`n[+] All 7 nodes and Tor have been launched!" -ForegroundColor Green