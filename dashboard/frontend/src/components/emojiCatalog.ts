export interface StandardEmoji {
  emoji: string
  name: string
  keywords: string
}

export interface EmojiCategory {
  id: string
  emojis: StandardEmoji[]
}

const entries = (values: Array<[string, string, string?]>): StandardEmoji[] =>
  values.map(([emoji, name, keywords = '']) => ({ emoji, name, keywords }))

// Unicode sequences supported by Twemoji and Discord. The browser renders the
// glyph with the local emoji font; Discord renders the selected sequence itself.
export const STANDARD_EMOJI_CATEGORIES: EmojiCategory[] = [
  { id: 'people', emojis: entries([
    ['😀','grinning face','笑顔 smile'],['😃','smiley face','笑顔 happy'],['😄','smile','笑顔 happy'],['😁','beaming face','笑顔 grin'],['😆','laughing face','笑う laugh'],['😅','sweat smile','汗'],['😂','tears of joy','泣き笑い'],['🤣','rolling laughing','爆笑'],['😊','blush','嬉しい'],['🙂','slightly smiling','笑顔'],['😉','wink','ウインク'],['😍','heart eyes','好き love'],['🥰','smiling hearts','好き love'],['😘','kiss','キス love'],['😎','sunglasses','かっこいい cool'],['🤔','thinking','考える'],['🫡','salute','敬礼'],['🤩','star struck','星'],['🥳','party face','お祝い'],['😭','crying','泣く sad'],['😡','angry','怒る'],['😱','scream','驚く'],['🤝','handshake','握手'],['👍','thumbs up','賛成 yes'],['👎','thumbs down','反対 no'],['👏','clapping','拍手'],['🙌','raising hands','万歳'],['🙏','folded hands','祈り thanks'],['💪','flexed biceps','力'],['👀','eyes','見る'],['❤️','red heart','ハート love'],['💔','broken heart','失恋'],['🔥','fire','炎 hot'],['✨','sparkles','きらきら'],['🎉','party popper','お祝い'],['💯','hundred points','満点']
  ]) },
  { id: 'nature', emojis: entries([
    ['🐶','dog','犬'],['🐱','cat','猫'],['🐭','mouse','ねずみ'],['🐹','hamster','ハムスター'],['🐰','rabbit','うさぎ'],['🦊','fox','きつね'],['🐻','bear','くま'],['🐼','panda','パンダ'],['🐨','koala','コアラ'],['🐯','tiger','虎'],['🦁','lion','ライオン'],['🐸','frog','かえる'],['🐵','monkey','猿'],['🐧','penguin','ペンギン'],['🐦','bird','鳥'],['🐤','chick','ひよこ'],['🦄','unicorn','ユニコーン'],['🐝','bee','蜂'],['🦋','butterfly','蝶'],['🌸','cherry blossom','桜'],['🌻','sunflower','ひまわり'],['🌱','seedling','芽'],['🌲','evergreen tree','木'],['🍀','four leaf clover','クローバー'],['🌈','rainbow','虹'],['☀️','sun','太陽 晴れ'],['🌙','moon','月'],['⭐','star','星'],['❄️','snowflake','雪'],['⚡','lightning','雷']
  ]) },
  { id: 'food', emojis: entries([
    ['🍎','apple','りんご'],['🍊','orange','みかん'],['🍋','lemon','レモン'],['🍇','grapes','ぶどう'],['🍓','strawberry','いちご'],['🍒','cherries','さくらんぼ'],['🍑','peach','桃'],['🍍','pineapple','パイナップル'],['🥝','kiwi','キウイ'],['🍅','tomato','トマト'],['🍔','hamburger','ハンバーガー'],['🍟','fries','ポテト'],['🍕','pizza','ピザ'],['🌭','hot dog','ホットドッグ'],['🍿','popcorn','ポップコーン'],['🍣','sushi','寿司'],['🍜','ramen','ラーメン'],['🍙','rice ball','おにぎり'],['🍰','cake','ケーキ'],['🍪','cookie','クッキー'],['🍫','chocolate','チョコ'],['☕','coffee','コーヒー'],['🍵','tea','お茶'],['🍺','beer','ビール']
  ]) },
  { id: 'activities', emojis: entries([
    ['⚽','soccer ball','サッカー'],['🏀','basketball','バスケットボール'],['🏈','football','アメフト'],['⚾','baseball','野球'],['🎾','tennis','テニス'],['🏐','volleyball','バレー'],['🎮','video game','ゲーム'],['🕹️','joystick','ゲーム'],['🎲','dice','サイコロ'],['🧩','puzzle','パズル'],['🎨','palette','絵 アート'],['🎸','guitar','ギター 音楽'],['🎧','headphones','音楽'],['🎤','microphone','歌'],['🎬','clapper board','映画'],['🏆','trophy','優勝'],['🥇','gold medal','金メダル'],['🎯','bullseye','目標'],['🎁','gift','プレゼント'],['🎈','balloon','風船']
  ]) },
  { id: 'travel', emojis: entries([
    ['🚗','car','車'],['🚕','taxi','タクシー'],['🚌','bus','バス'],['🚓','police car','警察'],['🚑','ambulance','救急車'],['🚒','fire engine','消防車'],['🚲','bicycle','自転車'],['✈️','airplane','飛行機'],['🚀','rocket','ロケット'],['🚢','ship','船'],['🏠','house','家'],['🏢','office building','ビル'],['🏫','school','学校'],['🏥','hospital','病院'],['⛺','tent','キャンプ'],['🗾','map of Japan','日本 地図'],['🌍','globe Europe Africa','地球'],['🌏','globe Asia Australia','地球 アジア']
  ]) },
  { id: 'objects', emojis: entries([
    ['⌚','watch','時計'],['📱','mobile phone','スマホ'],['💻','laptop','パソコン'],['⌨️','keyboard','キーボード'],['🖥️','desktop computer','コンピューター'],['📷','camera','カメラ'],['💡','light bulb','電球 アイデア'],['🔔','bell','通知'],['🔒','locked','鍵'],['🔑','key','鍵'],['🛠️','tools','工具'],['⚙️','gear','設定'],['📌','pushpin','ピン'],['📎','paperclip','クリップ'],['✏️','pencil','鉛筆'],['📝','memo','メモ'],['📅','calendar','カレンダー'],['📦','package','箱'],['💰','money bag','お金'],['💎','gem','宝石']
  ]) },
  { id: 'symbols', emojis: entries([
    ['✅','check mark button','完了 yes'],['❌','cross mark','拒否 no'],['⭕','hollow red circle','丸'],['❗','exclamation mark','注意'],['❓','question mark','質問'],['⚠️','warning','警告'],['🚫','prohibited','禁止'],['🔞','no one under eighteen','年齢制限'],['⬆️','up arrow','上'],['⬇️','down arrow','下'],['⬅️','left arrow','左'],['➡️','right arrow','右'],['🔄','counterclockwise arrows','更新'],['▶️','play button','再生'],['⏸️','pause button','一時停止'],['⏹️','stop button','停止'],['➕','plus','追加'],['➖','minus','削除'],['💬','speech balloon','会話'],['💤','zzz','睡眠']
  ]) },
  { id: 'flags', emojis: entries([
    ['🇯🇵','flag Japan','日本'],['🇺🇸','flag United States','アメリカ'],['🇬🇧','flag United Kingdom','イギリス'],['🇫🇷','flag France','フランス'],['🇩🇪','flag Germany','ドイツ'],['🇮🇹','flag Italy','イタリア'],['🇨🇦','flag Canada','カナダ'],['🇧🇷','flag Brazil','ブラジル'],['🇰🇷','flag South Korea','韓国'],['🇨🇳','flag China','中国'],['🇮🇳','flag India','インド'],['🇦🇺','flag Australia','オーストラリア'],['🏳️','white flag','白旗'],['🏴','black flag','黒旗'],['🏁','chequered flag','ゴール']
  ]) },
]
