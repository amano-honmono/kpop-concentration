# K-POP 顔当て神経衰弱

女性K-POPアイドルの顔写真で遊ぶ、1人用の神経衰弱です。**同じ人物の別の写真**をペアとしてそろえます。
写真は背景を消して、顔の位置と大きさをそろえてあるので、顔だけで見分ける遊びになります。

非営利の非公式ファンメイドで、各アーティスト・所属事務所とは関係ありません。

- `pipeline/` … 画像を準備する Python のパイプライン(写真集め → 顔検出 → 位置合わせ → 背景除去 → 書き出し)。手元で動かす
- `src/` … ゲーム本体(Vite + TypeScript、フレームワークなし)。ビルドすると静的な HTML / JS / CSS になり、GitHub Pages で遊べる

## 必要なもの

- Python 3.10〜3.12(MediaPipe が 3.13 に対応していないため)
- Node.js 20 以上

## セットアップ

```powershell
# Python(画像パイプライン)
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Node(ゲーム)
npm install
```

初回の画像処理のとき、学習済みモデル(合計 約220MB)を `cache/models/` にダウンロードします。

## 1. 画像を準備する

```powershell
.\.venv\Scripts\python.exe -m pipeline all       # 取得 → 加工 → 選択 をまとめて実行
.\.venv\Scripts\python.exe -m pipeline review    # 確認ページを開く
```

| コマンド | すること |
|---|---|
| `fetch` | Wikimedia Commons から候補の写真をダウンロードする(取得済みのメンバーは飛ばす。取り直すときは `--refresh`) |
| `process` | 顔検出・位置合わせ・背景除去をして `work/` に保存する(前回と同じ画像・設定なら作り直さない。`--force` で作り直す) |
| `build` | 1人あたり最大5枚を選び、`public/cards/` と `manifest.json` を書き出す。`work/review.html` も作る |
| `review` | 確認ページ(http://127.0.0.1:8765/)を開く |
| `all` | `fetch` → `process` → `build` |

対象を絞るときは `--members blackpink-jisoo,twice-nayeon` や `--groups twice,ive` を付けます。

### 確認ページで別人や失敗した画像を外す

`review` で開くページには、候補ごとに「元画像 / full / face」が並びます。

- 「除外」…その画像を使わない
- 「必ず使う」…その画像を優先して使う
- 「選び直す」…除外・固定を反映して選び直す

選んだ内容は `config/exclusions.yaml` に保存されます(手で編集してもかまいません)。

自動でも次のものは外しています。

- 顔が複数写っている、横を向いている、顔が小さい、顔が画像の端で切れている
- 同じメンバーの他の写真と顔が似ていない(別人の疑い)
- ほかに選んだ写真とほぼ同じ(連写・同じ写真の別トリミング)

同じ撮影(イベント)の写真は、服や髪型でペアがすぐわかってしまうので、できるだけ1枚ずつ選びます。

### 手動で写真を足す

`raw/<グループid>/<メンバーid>/` に画像(jpg / png / webp)を置いて、`process` と `build` を実行します。

```
raw/
  twice/
    nayeon/
      photo1.jpg
      credits.yaml   # 任意。クレジット画面に出す情報
```

`credits.yaml` の書き方:

```yaml
photo1.jpg:
  author: 撮影者の名前
  license: CC BY 4.0
  sourceUrl: https://example.com/original-page
  licenseUrl: https://creativecommons.org/licenses/by/4.0/
```

### 設定ファイル

- `config/groups.yaml` … グループとメンバー(日本語・英語・ハングルの名前、Commons のカテゴリ)。`enabled: false` で対象から外す
- `config/pipeline.yaml` … 取得枚数、顔の条件、切り抜き位置、選び方など

### Wikimedia のアクセス制限について

Wikimedia は2026年から、API などに1分あたりの上限を設けています。

- User-Agent に連絡先がないと 10回/分、連絡先(メールアドレスか URL)があると 200回/分
- 元画像の直接ダウンロードは強く制限されている(標準サイズのサムネイルを使う)

既定の設定は 9回/分なので、全員分(37人)の取得には2〜3時間かかります。
`config/pipeline.yaml` の `user_agent` に自分の連絡先を入れれば、`requests_per_minute` を120くらいまで上げられます。

## 2. ゲームで遊ぶ

```powershell
npm run dev        # http://localhost:5173/ で遊ぶ
npm run dev:lan    # 同じ Wi-Fi のスマホからも開けるようにする(表示される Network の URL を開く)
```

| コマンド | すること |
|---|---|
| `npm run build` | 型チェックして `dist/` に書き出す |
| `npm run preview` | `dist/` を確認用のサーバーで開く |
| `npm test` | 山札とゲーム進行のテスト |

### GitHub Pages で公開する

`main` ブランチに push すると、GitHub Actions(`.github/workflows/deploy.yml`)がテスト・ビルドして Pages に公開します。
リポジトリの Settings → Pages の Source は「GitHub Actions」にします。

カード画像はパイプラインで手元で作るので、写真を入れ替えたら `public/cards/` をコミットして push します。

```powershell
.\.venv\Scripts\python.exe -m pipeline build
git add public/cards config/exclusions.yaml
git commit -m "カード画像を更新"
git push
```

`vite.config.ts` で相対パス(`base: "./"`)にしてあるので、`https://<ユーザー名>.github.io/<リポジトリ名>/` のようなサブパスでもそのまま動きます。

### 遊び方と設定

- 裏返ったカードを2枚めくり、同じ人物ならペア成立。そろったカードには名前とグループが出ます
- ミスすると、めくった2枚が誰だったかを少しのあいだ表示します
- 設定画面
  - グループ:複数選べます。「同じグループのメンバーだけで出題」にすると、選んだ中から1グループだけで出題します(むずかしい)
  - ペアの数:6 / 8 / 12 / 18。メンバーが足りないときは、写真に余裕のある人が2組出ます
  - 画像:「髪型も見える」(full)/「顔だけ」(face、上級者向け)
  - 「同じ写真どうしでペアにする」:初心者向け
- クリア画面:時間・手数・ミス、今回のメンバー、取り違えた組み合わせ、ベスト記録(設定ごとにブラウザに保存)
- 設定画面の下の「画像のクレジット」で、写真の作者・ライセンス・元のページを見られます

## 構成

```
config/            groups.yaml, pipeline.yaml, exclusions.yaml
pipeline/          画像パイプライン(python -m pipeline)
  commons.py         Commons からの取得
  faces.py           顔検出(YuNet)・ランドマーク(MediaPipe Face Landmarker)・顔の特徴量(SFace)
  process.py         位置合わせ・背景除去(rembg)・face 用の楕円マスク
  build.py           画像の選択と書き出し
  review.py          確認ページとローカルサーバー
src/
  game/deck.ts       山札(ペアは同じ人の別の写真)
  game/engine.ts     ゲームの進行
  storage.ts         localStorage(設定・ベスト記録・取り違えの記録)
  ui/                設定・ゲーム・クリア・クレジットの各画面
public/cards/      カード画像と manifest.json(パイプラインが書き出す)
raw/               手動で置く写真
cache/, work/      ダウンロード・モデル・途中結果(消しても作り直せる)
```

## 後で足せるようにしてあること

- **苦手克服モード**:ミスした組み合わせは `storage.ts` の `recordMistakes` で `localStorage` に貯まっています(`loadConfusions()` で読める)。
  `deck.ts` の `MemberPicker` を、この記録で重み付けしたものに差し替えれば、似ている人どうしを多めに出せます
- **2人対戦**:`engine.ts` の `Game` はプレイヤーを配列で持ち、ミスで手番が替わります。画面側に手番とスコアの表示を足せば遊べます

## 写真のライセンスについて

カードの写真は Wikimedia Commons から、CC BY・CC BY-SA・パブリックドメイン・CC0 のものだけを使っています。
どの写真にも切り抜き・回転・拡大縮小・背景除去の加工をしていて、加工した写真(`public/cards/` の画像)は、それぞれ元の写真と同じライセンスで公開しています。
作者・ライセンス・元のページはゲームのクレジット画面と `public/cards/manifest.json` にあります。
ダウンロードした全候補のクレジットは `cache/commons/credits.json` にあります(リポジトリには含めない)。

写真がフリーライセンスでも、写っている本人の肖像権・パブリシティ権は別です。営利目的では使わないでください。

このリポジトリのコード(`pipeline/`、`src/` など)のライセンスは決めていません。
