# Host CaddyによるHTTPS

Linux HostのsystemdでCaddyを動かし、Stage／Prodの別ドメインを公開します。Docker内のDashboardはloopbackだけに公開し、Devはlocalhost HTTPで利用します。公開ドメインの正本は各app.envの `DASHBOARD_BASE_URL`、転送先ポートはdeployment.jsonです。Caddyには生成したサイト設定ファイルを配置します。

以下のShellコマンドはBashで、リポジトリルートから実行します。GitとDocker／Composeを[導入手順](setup.md)で準備します。Stage／Prodのbuild・start・healthが成功し、app.envに実ドメイン・対応するOAuth callback・`DASHBOARD_HTTPS_ONLY=true`を設定済みであることが前提です。公開切替は、設定の検証・配置・reloadの順に行います。

## HostとDNSを準備する

DNSのAをHostの公開IPv4に向けます。AAAAを作る場合はIPv6でもHostへ到達できることを確認します。Host Firewall・ルーター・Cloud側のFirewallでTCP 80／443を許可し、転送が必要ならCaddy Hostへ転送します。Dashboardの8000／8001はlocalhostから接続します。Caddyの自動HTTPSが証明書の取得・更新とHTTPからの転送を担当します。[公式仕様](https://caddyserver.com/docs/automatic-https)

ドメインと転送先を記載したサイト設定を生成し、DNSを照合します。

```sh
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy caddy-config --config-dir data/environments/stage --config-dir data/environments/prod --output artifacts/caddy/dns-check.caddy --overwrite
cat artifacts/caddy/dns-check.caddy
sudo ss -ltnp '( sport = :80 or sport = :443 )'
```

表示されたドメインを入力して照会します。digはディストリビューションのDNSツールパッケージで用意します。

```sh
read -r -p '確認する公開ドメイン: ' TUEKA_PUBLIC_DOMAIN
dig +short A "$TUEKA_PUBLIC_DOMAIN"
dig +short AAAA "$TUEKA_PUBLIC_DOMAIN"
```

既存Nginxなどが80／443を使用している場合は、後述の切替時間を確保してください。公式Debian/Ubuntuパッケージはインストール時にCaddyを起動します。別サイトを公開中の既存Caddyは停止・置換せず、設定を追加します。

## Caddyの導入（Debian／Ubuntu）

未導入のHostで管理者が実行します。OSパッケージはHost管理者が管理します。他のLinuxでは[公式インストール手順](https://caddyserver.com/docs/install)の該当ディストリビューションを使用します。

```sh
sudo apt-get update
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update
sudo apt-get install -y caddy
caddy version
systemctl status caddy --no-pager
```

## サイト設定を生成・検証する

```sh
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy caddy-config --config-dir data/environments/stage --config-dir data/environments/prod --output data/caddy/tueka.caddy
caddy validate --config data/caddy/tueka.caddy --adapter caddyfile
```

StageだけのHostではProdの `--config-dir` を省略します。再生成する場合は同じコマンド末尾へ `--overwrite` を付けます。ドメインはHTTPS・通常のDNS名・標準443番・Originのみを受け付け、環境違い、重複、callback不一致を拒否します。caddy-configでは複数環境の設定をまとめて生成できます。

Stageだけの初回生成:

```sh
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy caddy-config --config-dir data/environments/stage --output data/caddy/tueka.caddy
```

Stage／Prodの再生成:

```sh
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy caddy-config --config-dir data/environments/stage --config-dir data/environments/prod --output data/caddy/tueka.caddy --overwrite
caddy validate --config data/caddy/tueka.caddy --adapter caddyfile
```

生成ファイルは `/internal`・`/internal/*` を404にし、それ以外を環境別Dashboardへ転送します。アクセスログの既定値は無効です。Hostと転送ヘッダーはCaddyの標準動作を使用します。

## Backup・配置・reload

同じShell内で順に実行します。既存サイトを含む `/etc/caddy` を保存してから、Tueka専用ファイルだけを配置します。

```sh
TUEKA_CADDY_BACKUP="/var/backups/tueka-caddy/$(date -u +%Y%m%dT%H%M%SZ)"
sudo install -d -m 0700 "$TUEKA_CADDY_BACKUP"
sudo cp -a /etc/caddy "$TUEKA_CADDY_BACKUP/etc-caddy"
printf '%s\n' "$TUEKA_CADDY_BACKUP"
sudo install -d -m 0755 /etc/caddy/sites
sudo install -m 0644 data/caddy/tueka.caddy /etc/caddy/sites/tueka.caddy
sudoedit /etc/caddy/Caddyfile
```

エディタでは、他のサイトとグローバル設定を残し、トップレベルへ次の1行を追加します。同じファイルのimportと同じドメインのサイト設定は、それぞれ1件に揃えます。新規Hostの配布初期設定にある汎用 `:80` サイトは削除し、意図したドメインだけを公開します。

```caddyfile
import /etc/caddy/sites/tueka.caddy
```

全体設定の検証が成功してから起動・reloadします。失敗時はreloadせず修正、または下記Rollbackを行います。

```sh
sudo -u caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile && sudo systemctl enable --now caddy && sudo systemctl reload caddy
systemctl status caddy --no-pager
sudo journalctl -u caddy -n 50 --no-pager
```

reloadが成功すると設定が稼働中サービスへ反映されます。journalにエラーがないことと外部からの応答を確認します。[公式systemd運用](https://caddyserver.com/docs/running)

## 公開確認・Rollback

Host外からStageとProdそれぞれを確認します。次の入力は `https://` から始まる公開Originです。

```sh
read -r -p '確認するHTTPS Origin: ' TUEKA_PUBLIC_ORIGIN
curl -sS -o /dev/null -w '%{http_code}\n' "${TUEKA_PUBLIC_ORIGIN/https:/http:}/docs/"
curl -fsS -o /dev/null "$TUEKA_PUBLIC_ORIGIN/docs/"
curl -sS -o /dev/null -w '%{http_code}\n' "$TUEKA_PUBLIC_ORIGIN/internal/metrics"
curl -sS -o /dev/null -w '%{http_code}\n' "$TUEKA_PUBLIC_ORIGIN/api/openapi.json"
```

期待値はHTTPが308、Docsが成功、後半2件が404です。ブラウザーで公開証明書・OAuth Login/Logout・Secure Cookieを確認し、実Webhookは[Stage受入票](stage-acceptance.md)で確認します。code/tokenを含むURLやCookieを記録へ貼り付けません。

設定を戻す場合は、上で表示したBackupのパスを入力します。初回導入時だけTueka専用ファイルを取り除き、既存ファイルがあった場合はそれも復元します。復元対象はCaddyfileとTueka専用サイト設定です。他サイトのファイルを保全してください。

```sh
(
set -eu
read -r -p '復元するBackupディレクトリ: ' TUEKA_CADDY_BACKUP
sudo test -f "$TUEKA_CADDY_BACKUP/etc-caddy/Caddyfile"
sudo cp -a "$TUEKA_CADDY_BACKUP/etc-caddy/Caddyfile" /etc/caddy/Caddyfile
if sudo test -f "$TUEKA_CADDY_BACKUP/etc-caddy/sites/tueka.caddy"; then
  sudo cp -a "$TUEKA_CADDY_BACKUP/etc-caddy/sites/tueka.caddy" /etc/caddy/sites/tueka.caddy
else
  sudo rm -f /etc/caddy/sites/tueka.caddy
fi
sudo -u caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile && sudo systemctl reload caddy
)
```

## Nginxが稼働しているHostでの切替

既存Nginx設定・証明書を保管し、Nginx上の他サイトも移すか別Hostへ分離する段取りを先に決めます。切替時間に `sudo systemctl stop nginx` を実行して80／443を解放し、Caddyの起動・公開確認を行います。失敗時は `sudo systemctl stop caddy` の後に `sudo systemctl start nginx` でNginxの経路へ戻します。公開確認が完了するまでNginxの設定と証明書を保管します。80／443は切替先のサービスだけが使用する構成にします。

## 証明書と日常運用

公式systemdサービスのCaddyユーザーのデータ領域は通常 `/var/lib/caddy/.local/share/caddy` です。証明書・ACMEアカウント鍵を含むためアクセスを制限し、サービス更新で削除しないでください。Hostの暗号化Backup対象に含め、復元時は同じ所有者・権限を維持します。カスタムunitではHOME/XDG設定を確認して実際の保存先を記録します。

証明書更新失敗時はjournal、DNSのA/AAAA、80/443到達、システム時刻、データ領域の空き容量・所有者を確認します。繰り返しデータ領域を削除して再発行しないでください。journalの保持期間・閲覧権限をHost側で設定し、エラーに含まれるリクエスト情報は共有前に確認します。admin APIの2019番はHost内の管理用として扱います。

## 公開前の確認

DNS、公開証明書、systemd常駐、OAuth、Webhookは[Stage受入票](stage-acceptance.md)に沿って確認します。内部CAを用いた経路の自動検証は[開発者のテスト手順](../developer/TESTING.md)を参照してください。
