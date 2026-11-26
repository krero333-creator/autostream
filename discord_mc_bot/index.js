const { Client, GatewayIntentBits, EmbedBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle } = require('discord.js');
const mineflayer = require('mineflayer');
const { SocksClient } = require('socks');

const DISCORD_TOKEN = process.env.DISCORD_TOKEN;
const MC_HOST = 'eu.donutsmp.net';
const MC_PORT = 25565;
const MC_VERSION = process.env.MC_VERSION || false;
const PAY_ALERT_CHANNEL_ID = '1575550075243987124';

let proxyList = [];
let proxyIndex = 0;

async function fetchProxies() {
  try {
    const res = await fetch('https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=5000&country=all');
    const text = await res.text();
    const list = text.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
    if (list.length > 0) {
      proxyList = list;
      proxyIndex = 0;
      console.log(`[Proxy] Loaded ${proxyList.length} SOCKS5 proxies`);
    }
  } catch (e) {
    console.error('[Proxy] Failed to fetch:', e.message);
  }
}

function getNextProxy() {
  if (proxyList.length === 0) return null;
  const p = proxyList[proxyIndex % proxyList.length];
  proxyIndex++;
  const [host, port] = p.split(':');
  return { host, port: Number(port) };
}

const ACCOUNTS = {
  whats77: {
    username: 'whats77',
    channelId: '1575548695783674018',
    bot: null,
    online: false,
    balance: 'Неизвестно',
    embedMsgId: null,
  },
  osikox: {
    username: 'osikox',
    channelId: '1575548705707139273',
    bot: null,
    online: false,
    balance: 'Неизвестно',
    embedMsgId: null,
  },
};

const client = new Client({ intents: [GatewayIntentBits.Guilds] });

function buildEmbed(accKey) {
  const acc = ACCOUNTS[accKey];
  return new EmbedBuilder()
    .setTitle(`Аккаунт: ${acc.username}`)
    .setColor(acc.online ? 0x2ecc71 : 0xe74c3c)
    .addFields(
      { name: 'Статус', value: acc.online ? '🟢 На сервере' : '🔴 Не на сервере', inline: true },
      { name: 'Баланс', value: acc.balance, inline: true }
    )
    .setTimestamp();
}

function buildButtons(accKey) {
  return new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(`join_${accKey}`).setLabel('Зайти').setStyle(ButtonStyle.Success),
    new ButtonBuilder().setCustomId(`leave_${accKey}`).setLabel('Выйти').setStyle(ButtonStyle.Danger)
  );
}

async function updateEmbed(accKey) {
  const acc = ACCOUNTS[accKey];
  try {
    const channel = await client.channels.fetch(acc.channelId);
    if (!channel) return;
    const payload = { embeds: [buildEmbed(accKey)], components: [buildButtons(accKey)] };
    if (acc.embedMsgId) {
      const msg = await channel.messages.fetch(acc.embedMsgId).catch(() => null);
      if (msg) return await msg.edit(payload);
    }
    const sent = await channel.send(payload);
    acc.embedMsgId = sent.id;
  } catch (e) {
    console.error(`[Discord] Embed error for ${accKey}:`, e.message);
  }
}

async function startMcBot(accKey) {
  const acc = ACCOUNTS[accKey];
  if (acc.bot) return;
  acc.shouldReconnect = true;

  if (proxyList.length === 0) await fetchProxies();
  const proxy = acc.workingProxy || getNextProxy();
  acc.currentProxy = proxy;

  const bot = mineflayer.createBot({
    host: MC_HOST,
    port: MC_PORT,
    username: acc.username,
    auth: 'microsoft',
    version: MC_VERSION,
    profilesFolder: `./auth_cache_${accKey}`,
    connect: proxy
      ? (client) => {
          SocksClient.createConnection({
            proxy: { host: proxy.host, port: proxy.port, type: 5 },
            command: 'connect',
            destination: { host: MC_HOST, port: MC_PORT },
            timeout: 8000,
          })
            .then((info) => {
              client.setSocket(info.socket);
              client.emit('connect');
            })
            .catch((err) => {
              console.error(`[Proxy ${accKey}] Failed (${proxy.host}:${proxy.port}):`, err.message);
              acc.workingProxy = null;
              acc.bot = null;
              if (acc.shouldReconnect) {
                setTimeout(() => startMcBot(accKey), 1000);
              }
            });
        }
      : undefined,
    onMsaCode: async (data) => {
      try {
        const ch = await client.channels.fetch(acc.channelId);
        if (ch) {
          await ch.send(`🔐 **Авторизация ${acc.username}**: перейди на ${data.verification_uri} и введи код: \`${data.user_code}\``);
        }
      } catch (e) {
        console.error('[MSA] Error:', e.message);
      }
    },
  });

  acc.bot = bot;

  bot.on('login', () => {
    acc.online = true;
    acc.workingProxy = acc.currentProxy;
    updateEmbed(accKey);
  });

  bot.on('scoreboardTitleChanged', () => parseScoreboard(accKey));
  bot.on('scoreboardScore', () => parseScoreboard(accKey));

  bot.on('messagestr', async (message) => {
    // Ловим сообщения вида: "whats77 paid you $ 1" или "whats77 paid you $1B"
    const match = message.match(/^(\S+)\s+paid\s+you\s+\$\s*([0-9.,]+[KMBT]?)/i);
    if (match) {
      const sender = match[1];
      const amount = match[2];
      try {
        const payCh = await client.channels.fetch(PAY_ALERT_CHANNEL_ID);
        if (payCh) {
          await payCh.send(`@here ${sender} paid you ${amount}$ (на аккаунт **${acc.username}**)`);
        }
      } catch (e) {
        console.error('[Discord] Pay alert error:', e.message);
      }
    }
  });

  bot.on('end', () => {
    acc.online = false;
    acc.bot = null;
    updateEmbed(accKey);
    if (acc.shouldReconnect) {
      setTimeout(() => startMcBot(accKey), 3000);
    }
  });

  bot.on('kicked', (reason) => {
    console.error(`[MC ${accKey}] Kicked:`, JSON.stringify(reason));
    acc.workingProxy = null;
  });

  bot.on('error', (err) => {
    console.error(`[MC ${accKey}] Error:`, err.message);
    acc.workingProxy = null;
  });
}

function parseScoreboard(accKey) {
  const acc = ACCOUNTS[accKey];
  if (!acc.bot || !acc.bot.scoreboard || !acc.bot.scoreboard.sidebar) return;
  const items = acc.bot.scoreboard.sidebar.items || [];
  for (const item of items) {
    const text = (item.displayName?.toString() || item.name || '').replace(/§[0-9a-fk-or]/gi, '').trim();
    if (text.includes('$')) {
      if (acc.balance !== text) {
        acc.balance = text;
        updateEmbed(accKey);
      }
      break;
    }
  }
}

client.once('ready', async () => {
  console.log(`[Discord] Logged in as ${client.user.tag}`);
  for (const accKey of Object.keys(ACCOUNTS)) {
    await updateEmbed(accKey);
  }
});

client.on('interactionCreate', async (interaction) => {
  if (!interaction.isButton()) return;
  const [action, accKey] = interaction.customId.split('_');
  const acc = ACCOUNTS[accKey];
  if (!acc) return;

  await interaction.deferUpdate();
  if (action === 'join') {
    startMcBot(accKey);
  } else if (action === 'leave') {
    acc.shouldReconnect = false;
    if (acc.bot) {
      acc.bot.quit();
      acc.bot = null;
    }
    acc.online = false;
    await updateEmbed(accKey);
  }
});

client.login(DISCORD_TOKEN);
