<script setup>
import {computed} from "vue";

const BRAND = {
  name: "Sumire Vox Bot",
  tagline: "VOICEVOXで、Discordの会話をもっと楽しく。",
};

const config = {
  discordClientId: import.meta.env.VITE_DISCORD_CLIENT_ID,
  discordRedirectUri: import.meta.env.VITE_DISCORD_REDIRECT_URI,
  discordInviteUrl: import.meta.env.VITE_DISCORD_INVITE_URL,
  stripeCheckoutUrl: import.meta.env.VITE_STRIPE_CHECKOUT_URL,
};

const isConfigured = computed(() => {
  return Boolean(config.discordClientId && config.discordRedirectUri && config.discordInviteUrl);
});

function base64UrlEncode(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

async function sha256(text) {
  const data = new TextEncoder().encode(text);
  return crypto.subtle.digest("SHA-256", data);
}

function randomString(length = 64) {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~";
  const bytes = crypto.getRandomValues(new Uint8Array(length));
  return Array.from(bytes, (b) => chars[b % chars.length]).join("");
}

/**
 * Discord OAuth2 (Authorization Code + PKCE)
 * - ここでは「ログイン開始」だけ実装（Discordにリダイレクト）
 * - リダイレクト先で code を受け取り、サーバーで token 交換するのが一般的
 *   (PKCEを使う場合はクライアント完結も可能だが、運用・セキュリティ観点でバックエンド推奨)
 */
async function loginWithDiscord() {
  if (!config.discordClientId || !config.discordRedirectUri) {
    alert("Discord OAuthの環境変数が未設定です（VITE_DISCORD_CLIENT_ID / VITE_DISCORD_REDIRECT_URI）");
    return;
  }

  const state = randomString(32);
  const codeVerifier = randomString(64);
  const codeChallenge = base64UrlEncode(await sha256(codeVerifier));

  sessionStorage.setItem("discord_oauth_state", state);
  sessionStorage.setItem("discord_pkce_verifier", codeVerifier);

  const params = new URLSearchParams({
    client_id: config.discordClientId,
    redirect_uri: config.discordRedirectUri,
    response_type: "code",
    scope: "identify guilds",
    state,
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
    prompt: "none",
  });

  window.location.href = `https://discord.com/oauth2/authorize?${params.toString()}`;
}

function goInvite() {
  if (!config.discordInviteUrl) {
    alert("招待URLが未設定です（VITE_DISCORD_INVITE_URL）");
    return;
  }
  window.open(config.discordInviteUrl, "_blank", "noopener,noreferrer");
}

function buyPremium() {
  if (!config.stripeCheckoutUrl) {
    alert("Stripeの購入URLが未設定です（VITE_STRIPE_CHECKOUT_URL）");
    return;
  }
  window.open(config.stripeCheckoutUrl, "_blank", "noopener,noreferrer");
}
</script>

<template>
  <div class="page">
    <header class="header">
      <a class="logo" href="#" aria-label="Sumire Vox Bot">
        <span class="logoMark" aria-hidden="true"></span>
        <span class="logoText">{{ BRAND.name }}</span>
      </a>

      <nav class="nav">
        <a href="#features">機能</a>
        <a href="#howto">使い方</a>
        <a href="#premium">プレミアム</a>
      </nav>

      <div class="headerCtas">
        <button class="btn primary" type="button" @click="loginWithDiscord">Discordでログイン</button>
      </div>
    </header>

    <main id="top" class="main">
      <section class="hero">
        <div class="heroLeft">
          <p class="pill">Discord × VOICEVOX</p>
          <h1 class="heroTitle">
            {{ BRAND.name }}
          </h1>
          <p class="heroLead">
            {{ BRAND.tagline }}<br/>
            サーバーの読み上げ体験を、かんたんに。
          </p>

          <div class="heroButtons">
            <button class="btn primary big" type="button" @click="goInvite">サーバーに導入</button>
            <button class="btn outline big" type="button" @click="buyPremium">プレミアムを購入</button>
          </div>

          <p class="note" v-if="!isConfigured">
            ※ 現在は環境変数が未設定のため、ボタンが正しく動きません（下の手順を参照）
          </p>
        </div>

        <div class="heroRight" aria-hidden="true">
          <!-- Discord風 読み上げプレビュー（作り直し） -->
          <div class="dPreview" role="img" aria-label="Discord風の読み上げプレビュー">
            <div class="dChrome">
              <div class="dTopDots" aria-hidden="true">
                <span class="dDot"></span><span class="dDot"></span><span class="dDot"></span>
              </div>
              <div class="dChannel">
                <span class="dChannelName">#聞き専</span>
              </div>
              <div class="dTopRight" aria-hidden="true">
                <span class="dPill">Discord</span>
              </div>
            </div>

            <div class="dBody">
              <div class="dDayDivider" aria-hidden="true">
                <span class="dLine"></span>
                <span class="dDay">今日</span>
                <span class="dLine"></span>
              </div>

              <div class="dMsg">
                <div class="dAvatar dAvatar--you" aria-hidden="true"></div>
                <div class="dContent">
                  <div class="dMeta">
                    <span class="dName dName--you">You</span>
                    <span class="dTime">12:01</span>
                  </div>
                  <div class="dText">
                    <span class="dSlash">/join</span>
                  </div>
                </div>
              </div>

              <div class="dMsg">
                <div class="dAvatar dAvatar--bot" aria-hidden="true"></div>
                <div class="dContent">
                  <div class="dMeta">
                    <span class="dName dName--bot">SumireVoxBot</span>
                    <span class="dBotTag">BOT</span>
                    <span class="dTime">12:01</span>
                  </div>

                  <div class="dEmbed dEmbed--success">
                    <div class="dEmbedBar" aria-hidden="true"></div>
                    <div class="dEmbedBody">
                      <div class="dEmbedTitle">✅ 接続しました</div>
                      <div class="dEmbedText">
                        VC-1 に接続しました。<br/>
                        このチャンネルのチャットを読み上げます。
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div class="dMsg">
                <div class="dAvatar dAvatar--you" aria-hidden="true"></div>
                <div class="dContent">
                  <div class="dMeta">
                    <span class="dName dName--you">You</span>
                    <span class="dTime">12:02</span>
                  </div>
                  <div class="dText">
                    こんにちは！今日もよろしく！
                  </div>
                </div>
              </div>

              <div class="dTyping" aria-hidden="true">
                <span class="dTypingDot"></span><span class="dTypingDot"></span><span class="dTypingDot"></span>
                <span class="dTypingText">You が入力中…</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="features" class="section">
        <h2 class="sectionTitle">主な機能</h2>
        <p class="sectionLead">読み上げに必要な機能を、シンプルに揃えました。</p>

        <div class="grid">
          <article class="card">
            <h3>ボイスチャンネルでテキストを読み上げ</h3>
            <p>
              指定したチャンネルに送信されたメッセージを読み上げます。読み上げ音声はVOICEVOX ENGINEを利用しています。
            </p>
          </article>

          <article class="card">
            <h3>入退出の読み上げ通知</h3>
            <p>
              ボイスチャンネルに参加・退出した方の名前を読み上げて、ボイスチャンネルの入退出を通知します。
            </p>
          </article>

          <article class="card">
            <h3>ボイスチャンネルの自動接続</h3>
            <p>
              あらかじめ指定したボイスチャンネルにユーザーが参加した場合、自動的に接続して読み上げを開始します。
            </p>
          </article>

          <article class="card">
            <h3>読み上げの声を自由にカスタマイズ</h3>
            <p>
              話者・ピッチ・スピードなどを自由に設定できます。あなただけの読み上げ音声を提供します。
            </p>
          </article>
        </div>
      </section>

      <section id="howto" class="section">
        <h2 class="sectionTitle">使い方</h2>

        <div class="steps">
          <div class="step">
            <div class="stepNum">1</div>
            <div>
              <div class="stepTitle">サーバーに招待</div>
              <div class="stepText">「サーバーに導入」からBotを追加します。</div>
            </div>
          </div>

          <div class="step">
            <div class="stepNum">2</div>
            <div>
              <div class="stepTitle">ボイスチャンネルで開始</div>
              <div class="stepText"><code>/join</code> で参加、テキストを読み上げます。</div>
            </div>
          </div>

          <div class="step">
            <div class="stepNum">3</div>
            <div>
              <div class="stepTitle">設定をカスタマイズ</div>
              <div class="stepText">
                <code>/set_voice</code>で話者・速度・ピッチなどを好みに合わせて調整できます。
                <p><code>/config</code>でサーバーごとに機能の設定を行えます。</p>
              </div>
            </div>
          </div>
        </div>

        <div class="callout">
          <div>
            <div class="calloutTitle">まずは導入して試してみましょう</div>
            <div class="calloutText">サーバーの雰囲気に合う読み上げを、VOICEVOXで。</div>
          </div>
          <div class="calloutBtns">
            <button class="btn primary" type="button" @click="goInvite">招待する</button>
          </div>
        </div>
      </section>

      <section id="premium" class="section">
        <h2 class="sectionTitle">プレミアム</h2>
        <p class="sectionLead">
          有料プランの決済はStripeを利用します。
        </p>

        <div class="premium">
          <div class="plan">
            <div class="planName">Premium</div>
            <div class="planPrice">¥ 1,000 / 月</div>
            <ul class="planList">
              <li>（例）優先読み上げ / 高品質設定</li>
              <li>（例）辞書枠の拡張</li>
              <li>（例）サポート優先</li>
            </ul>
            <button class="btn outline big" type="button" @click="buyPremium">Stripeで購入</button>
            <div class="planNote">※価格・特典は後から差し替えできます。</div>
          </div>

          <div class="faq">
            <h3>よくある質問</h3>
            <details>
              <summary>Discordログインは何のため？</summary>
              <p>
                サーバー設定の管理画面（読み上げチャンネル、辞書管理など）を実装する際に必要になります。
              </p>
            </details>
            <details>
              <summary>決済後の特典反映はどうする？</summary>
              <p>
                Stripe Webhookで「購入完了」を受け、DBに紐付け、Discordロール付与などを自動化する構成が一般的です。
              </p>
            </details>
          </div>
        </div>
      </section>
    </main>

    <footer class="footer">
      <div class="footerInner">
        <div class="footerBrandCol">
          <div class="footerName">{{ BRAND.name }}</div>
          <div class="footerSub">VOICEVOXで、Discordの会話をもっと楽しく。</div>
          <div class="footerPowered">Powered by VOICEVOX</div>
        </div>

        <div class="footerNav">
          <div class="footerCol">
            <div class="footerColTitle">ページ一覧</div>
            <a href="#premium">プレミアム</a>
            <a href="#">ダッシュボード</a>
            <a href="#howto">コマンド</a>
          </div>
          <div class="footerCol">
            <div class="footerColTitle">その他のリンク</div>
            <a href="#" target="_blank" rel="noopener">X</a>
            <a href="#" target="_blank" rel="noopener">Discord</a>
            <a href="#" target="_blank" rel="noopener">GitHub</a>
          </div>
          <div class="footerCol">
            <div class="footerColTitle">規約とポリシー</div>
            <a href="#">利用規約</a>
            <a href="#">個人情報保護方針</a>
            <a href="#">払い戻しポリシー</a>
          </div>
        </div>
      </div>
    </footer>
  </div>
</template>

<style>
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html, body {
  margin: 0;
  padding: 0;
  min-height: 100vh;
  background: #f7f9ff;
  scroll-behavior: smooth;
}

</style>

<style scoped>
.page {
  --bg0: #f7f9ff;
  --bg1: #eef2ff;
  --surface: rgba(255, 255, 255, 0.72);
  --stroke: rgba(66, 84, 140, 0.15);

  --text: #1b2340;
  --muted: rgba(27, 35, 64, 0.72);

  --primary: #7b90ff;
  --primary2: #a7b6ff;
  --accent: #8fd5ff;

  --shadow: 0 16px 40px rgba(20, 25, 50, 0.10);

  color: var(--text);
  padding-top: 14px;
  background: radial-gradient(1200px 700px at 20% 10%, rgba(167, 182, 255, 0.55), transparent 60%),
  radial-gradient(900px 600px at 80% 0%, rgba(143, 213, 255, 0.40), transparent 55%),
  linear-gradient(180deg, var(--bg0), var(--bg1));
}

.header {
  position: sticky;
  top: 0;
  z-index: 20;

  width: min(1100px, calc(100% - 28px));
  margin: 14px auto 0;
  padding: 12px 14px;

  display: flex;
  align-items: center;
  gap: 14px;

  background: var(--surface);
  backdrop-filter: blur(12px);
  border: 1px solid var(--stroke);
  border-radius: 14px;
  box-shadow: 0 8px 24px rgba(20, 25, 50, 0.06);
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  color: inherit;
  font-weight: 700;
}

.logoMark {
  width: 28px;
  height: 28px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--primary2), var(--accent));
  box-shadow: 0 10px 20px rgba(123, 144, 255, 0.25);
}

.logoText {
  letter-spacing: 0.2px;
}

.nav {
  margin-left: auto;
  display: flex;
  gap: 14px;
}

.nav a {
  text-decoration: none;
  color: var(--muted);
  font-weight: 600;
  padding: 8px 10px;
  border-radius: 10px;
}

.nav a:hover {
  background: rgba(123, 144, 255, 0.10);
  color: var(--text);
}

.headerCtas {
  display: flex;
  gap: 10px;
}

.main {
  width: min(1100px, calc(100% - 28px));
  margin: 0 auto;
  padding: 26px 0 50px;
}

.hero {
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  gap: 18px;
  align-items: center;
  padding: 18px 0 10px;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  color: rgba(27, 35, 64, 0.75);
  background: rgba(255, 255, 255, 0.55);
  border: 1px solid var(--stroke);
  padding: 7px 10px;
  border-radius: 999px;
}

.heroTitle {
  font-size: clamp(34px, 4vw, 52px);
  margin: 14px 0 10px;
  letter-spacing: -0.4px;
}

.heroLead {
  color: var(--muted);
  line-height: 1.7;
  font-size: 16px;
  margin: 0 0 18px;
}

.heroButtons {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.note {
  margin-top: 12px;
  color: rgba(27, 35, 64, 0.60);
  font-size: 13px;
}

.dPreview {
  --d-bg: #313338;
  --d-top: #2b2d31;
  --d-panel: #1e1f22;
  --d-text: rgba(255, 255, 255, 0.92);
  --d-muted: rgba(255, 255, 255, 0.64);
  --d-faint: rgba(255, 255, 255, 0.38);
  --d-stroke: rgba(0, 0, 0, 0.45);
  --d-blurple: #5865f2;
  --d-green: #23a559;

  border-radius: 18px;
  border: 1px solid var(--d-stroke);
  background: var(--d-bg);
  box-shadow: 0 18px 46px rgba(0, 0, 0, 0.35);
  overflow: hidden;
}

.dChrome {
  height: 44px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 0 12px;
  background: var(--d-top);
  border-bottom: 1px solid var(--d-stroke);
}

.dTopDots {
  display: flex;
  gap: 8px;
  align-items: center;
}

.dDot {
  width: 10px;
  height: 10px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.18);
}

.dDot:nth-child(1) {
  background: rgba(255, 99, 140, 0.55);
}

.dDot:nth-child(2) {
  background: rgba(255, 205, 70, 0.55);
}

.dDot:nth-child(3) {
  background: rgba(92, 220, 154, 0.55);
}

.dChannel {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--d-text);
  font-weight: 800;
  min-width: 0;
}

.dChannelName {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dTopRight {
  display: inline-flex;
  justify-content: flex-end;
}

.dPill {
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 0.2px;
  color: rgba(255, 255, 255, 0.82);
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(0, 0, 0, 0.25);
}

.dBody {
  padding: 12px 0 14px;
}

.dDayDivider {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 10px;
  padding: 8px 14px 10px;
  color: var(--d-faint);
}

.dLine {
  height: 1px;
  background: rgba(255, 255, 255, 0.08);
}

.dDay {
  font-size: 12px;
  font-weight: 800;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(0, 0, 0, 0.25);
}

.dMsg {
  display: grid;
  grid-template-columns: 44px 1fr;
  gap: 10px;
  padding: 8px 14px;
}

.dAvatar {
  width: 36px;
  height: 36px;
  border-radius: 999px;
  margin-top: 2px;
  border: 1px solid rgba(0, 0, 0, 0.35);
  box-shadow: 0 10px 18px rgba(0, 0, 0, 0.25);
}

.dAvatar--you {
  background: radial-gradient(circle at 30% 30%, rgba(167, 182, 255, 0.95), rgba(123, 144, 255, 0.45));
}

.dAvatar--bot {
  background: radial-gradient(circle at 30% 30%, rgba(88, 101, 242, 0.95), rgba(35, 165, 89, 0.35));
}

.dContent {
  min-width: 0;
}

.dMeta {
  display: flex;
  align-items: baseline;
  gap: 8px;
  line-height: 1.1;
}

.dName {
  font-weight: 900;
  color: var(--d-text);
}

.dName--you {
  color: rgba(255, 255, 255, 0.90);
}

.dName--bot {
  color: rgba(255, 255, 255, 0.92);
}

.dTime {
  font-size: 12px;
  color: var(--d-faint);
  font-weight: 700;
}

.dBotTag {
  font-size: 11px;
  font-weight: 900;
  padding: 2px 6px;
  border-radius: 6px;
  background: var(--d-blurple);
  color: white;
  transform: translateY(-1px);
}

.dText {
  margin-top: 4px;
  color: rgba(255, 255, 255, 0.88);
  font-size: 14px;
  line-height: 1.55;
  word-break: break-word;
}

.dSlash {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-weight: 800;
  color: rgba(255, 255, 255, 0.92);
  background: rgba(0, 0, 0, 0.18);
  border: 1px solid rgba(0, 0, 0, 0.35);
  padding: 2px 8px;
  border-radius: 8px;
}

.dEmbed {
  margin-top: 8px;
  display: grid;
  grid-template-columns: 6px 1fr;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.42);
  background: rgba(0, 0, 0, 0.16);
}

.dEmbedBar {
  background: var(--d-green);
}

.dEmbedBody {
  padding: 10px 12px;
}

.dEmbedTitle {
  font-weight: 900;
  color: rgba(255, 255, 255, 0.94);
  margin-bottom: 4px;
}

.dEmbedText {
  color: rgba(255, 255, 255, 0.74);
  font-size: 13px;
  line-height: 1.45;
}

/* typing indicator */
.dTyping {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 6px 14px 0;
  padding: 8px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(0, 0, 0, 0.30);
  color: var(--d-muted);
  font-size: 12px;
  font-weight: 800;
}

.dTypingDot {
  width: 6px;
  height: 6px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.55);
  animation: d-bounce 1.1s infinite ease-in-out;
}

.dTypingDot:nth-child(2) {
  animation-delay: 0.12s;
  opacity: 0.85;
}

.dTypingDot:nth-child(3) {
  animation-delay: 0.24s;
  opacity: 0.70;
}

.dTypingText {
  margin-left: 4px;
  color: rgba(255, 255, 255, 0.62);
}

@keyframes d-bounce {
  0%, 80%, 100% {
    transform: translateY(0);
  }
  40% {
    transform: translateY(-3px);
  }
}

.section {
  padding: 34px 0 6px;
}

.sectionTitle {
  font-size: 26px;
  margin: 0 0 6px;
}

.sectionLead {
  margin: 0 0 16px;
  color: var(--muted);
  line-height: 1.7;
}

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.card {
  background: rgba(255, 255, 255, 0.65);
  border: 1px solid var(--stroke);
  border-radius: 16px;
  padding: 14px 14px;
  box-shadow: 0 10px 24px rgba(20, 25, 50, 0.06);
}

.card h3 {
  margin: 0 0 6px;
  font-size: 16px;
}

.card p {
  margin: 0;
  color: var(--muted);
  line-height: 1.7;
  font-size: 14px;
}

.steps {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
  margin-top: 12px;
}

.step {
  display: flex;
  gap: 12px;
  align-items: flex-start;

  background: rgba(255, 255, 255, 0.62);
  border: 1px solid var(--stroke);
  border-radius: 16px;
  padding: 12px 12px;
}

.stepNum {
  width: 34px;
  height: 34px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  font-weight: 800;
  background: linear-gradient(135deg, rgba(123, 144, 255, 0.35), rgba(143, 213, 255, 0.25));
  border: 1px solid rgba(123, 144, 255, 0.20);
}

.stepTitle {
  font-weight: 800;
  margin-bottom: 4px;
}

.stepText {
  color: var(--muted);
  line-height: 1.7;
}

code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.95em;
  padding: 2px 6px;
  border-radius: 8px;
  border: 1px solid var(--stroke);
  background: rgba(255, 255, 255, 0.65);
}

.callout {
  margin-top: 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;

  padding: 14px 14px;
  border-radius: 18px;
  border: 1px solid rgba(123, 144, 255, 0.22);
  background: linear-gradient(135deg, rgba(167, 182, 255, 0.34), rgba(143, 213, 255, 0.22));
}

.calloutTitle {
  font-weight: 900;
  margin-bottom: 2px;
}

.calloutText {
  color: rgba(27, 35, 64, 0.70);
}

.calloutBtns {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.premium {
  display: grid;
  grid-template-columns: 0.95fr 1.05fr;
  gap: 12px;
  margin-top: 10px;
}

.plan, .faq {
  background: rgba(255, 255, 255, 0.65);
  border: 1px solid var(--stroke);
  border-radius: 18px;
  padding: 14px 14px;
  box-shadow: 0 10px 24px rgba(20, 25, 50, 0.06);
}

.planName {
  font-weight: 900;
  font-size: 18px;
}

.planPrice {
  color: rgba(27, 35, 64, 0.70);
  margin: 6px 0 10px;
}

.planList {
  margin: 0 0 12px;
  padding-left: 18px;
  color: var(--muted);
  line-height: 1.7;
}

.planNote {
  margin-top: 8px;
  font-size: 12px;
  color: rgba(27, 35, 64, 0.60);
}

.faq h3 {
  margin: 0 0 10px;
}

details {
  border: 1px solid var(--stroke);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.55);
  padding: 10px 10px;
  margin-bottom: 10px;
}

summary {
  cursor: pointer;
  font-weight: 800;
}

details p {
  margin: 8px 0 0;
  color: var(--muted);
  line-height: 1.7;
}

.footer {
  margin-top: 50px;
  padding: 0 0 50px;
}

.footerInner {
  width: min(1100px, calc(100% - 28px));
  margin: 0 auto;
  padding: 40px 30px;

  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 40px;

  border-radius: 24px;
  border: 1px solid var(--stroke);
  background: rgba(255, 255, 255, 0.55);
}

.footerBrandCol {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.footerName {
  font-weight: 900;
  font-size: 20px;
  letter-spacing: -0.2px;
}

.footerSub {
  color: var(--muted);
  font-size: 14px;
  line-height: 1.5;
}

.footerPowered {
  margin-top: 8px;
  color: rgba(27, 35, 64, 0.5);
  font-size: 12px;
  font-weight: 700;
}

.footerNav {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

.footerCol {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.footerColTitle {
  font-weight: 800;
  font-size: 14px;
  color: var(--text);
  margin-bottom: 4px;
}

.footerCol a {
  text-decoration: none;
  color: var(--muted);
  font-size: 14px;
  font-weight: 600;
  transition: color 0.2s;
}

.footerCol a:hover {
  color: var(--primary);
}

.btn {
  border: 1px solid transparent;
  border-radius: 12px;
  padding: 9px 12px;
  font-weight: 800;
  color: var(--text);
  background: rgba(255, 255, 255, 0.55);
  cursor: pointer;
}

.btn:hover {
  transform: translateY(-1px);
  transition: 140ms transform ease;
}

.btn.primary {
  color: #0f1633;
  background: linear-gradient(135deg, var(--primary2), var(--accent));
  border-color: rgba(123, 144, 255, 0.20);
  box-shadow: 0 12px 22px rgba(123, 144, 255, 0.22);
}

.btn.ghost {
  background: rgba(255, 255, 255, 0.40);
  border-color: var(--stroke);
}

.btn.outline {
  background: transparent;
  border-color: rgba(123, 144, 255, 0.30);
}

.btn.big {
  padding: 12px 14px;
  border-radius: 14px;
}

@media (max-width: 920px) {
  .hero {
    grid-template-columns: 1fr;
  }

  .nav {
    display: none;
  }

  .premium {
    grid-template-columns: 1fr;
  }

  .grid {
    grid-template-columns: 1fr;
  }

  .footerInner {
    grid-template-columns: 1fr;
    padding: 30px 20px;
  }

  .footerNav {
    grid-template-columns: repeat(2, 1fr);
    gap: 30px;
  }
}
</style>