param(
    [string]$SshTarget = "uk-9950x",
    [string]$UnitSource = "$PSScriptRoot\dmgongheguo-emulator@.service"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $UnitSource -PathType Leaf)) {
    throw "systemd unit 不存在: $UnitSource"
}

$remoteStaging = "/tmp/dmgongheguo-emulator@.service"
scp -- $UnitSource "${SshTarget}:$remoteStaging"
if ($LASTEXITCODE -ne 0) {
    throw "scp systemd unit 失败"
}

ssh -- $SshTarget @"
set -eu
test -c /dev/kvm
test -x /opt/android-sdk/emulator/emulator
test -x /opt/android-sdk/platform-tools/adb
install -m 0644 '$remoteStaging' /etc/systemd/system/dmgongheguo-emulator@.service
rm -f '$remoteStaging'
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/dmgongheguo-emulator@.service
test "`$(systemctl is-enabled dmgongheguo-emulator@poc34.service 2>/dev/null || true)" != enabled
systemctl show dmgongheguo-emulator@poc34.service -p LoadState -p ActiveState --no-pager
"@
if ($LASTEXITCODE -ne 0) {
    throw "远程安装或验证 systemd unit 失败"
}
