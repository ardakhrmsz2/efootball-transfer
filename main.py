import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import re

# --- VERİ TABANI (KAYIT) AYARLARI ---
OYUNCU_DOSYASI = "oyuncular.json"
TAKIM_DOSYASI = "takimlar.json"


# Sayı dönüştürme araçları (Matematik işlemleri ve kasadan para düşmek için)
def sayiya_cevir(metin):
    sayilar = re.sub(r'\D', '', str(metin))  # Harfleri ve noktaları atıp sadece sayıları alır
    return int(sayilar) if sayilar else 0


def butce_yaz(sayi):
    return f"{sayi:,}".replace(",", ".") + " Euro"  # Sayıyı tekrar "15.000.000 Euro" formatına sokar


# Bot açıldığında eski verileri dosyadan okuma
def veri_yukle():
    global oyuncular, takimlar
    if os.path.exists(OYUNCU_DOSYASI):
        with open(OYUNCU_DOSYASI, "r", encoding="utf-8") as f:
            oyuncular = json.load(f)
    else:
        oyuncular = {}

    if os.path.exists(TAKIM_DOSYASI):
        with open(TAKIM_DOSYASI, "r", encoding="utf-8") as f:
            gecici_takimlar = json.load(f)
            takimlar = {}
            # Eski veri tabanını otomatik yeni sisteme (Menajerli sisteme) uydurma
            for t, veri in gecici_takimlar.items():
                if isinstance(veri, str):
                    takimlar[t] = {"butce": veri, "yonetici_id": None}
                else:
                    takimlar[t] = veri
    else:
        takimlar = {}


# Bir ekleme/silme yapıldığında dosyayı güncelleme
def veri_kaydet():
    with open(OYUNCU_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(oyuncular, f, ensure_ascii=False, indent=4)
    with open(TAKIM_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(takimlar, f, ensure_ascii=False, indent=4)


# Verileri yüklüyoruz
veri_yukle()


# --- BOT AYARLARI ---
class FutbolBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        try:
            synced = await self.tree.sync()
            print(f"✅ Başarıyla {len(synced)} slash komutu senkronize edildi.")
        except Exception as e:
            print(f"Senkronizasyon hatası: {e}")


bot = FutbolBot()


@bot.event
async def on_ready():
    print(f"✅ {bot.user.name} çalışıyor ve veriler başarıyla yüklendi!")


# --- TRANSFER TEKLİFİ BUTON SİSTEMİ ---
class TransferView(discord.ui.View):
    def __init__(self, alici_takim, satici_takim, teklif_miktari, oyuncu_adi, yonetici_id):
        super().__init__(timeout=None)
        self.alici_takim = alici_takim
        self.satici_takim = satici_takim
        self.teklif_miktari = teklif_miktari
        self.oyuncu_adi = oyuncu_adi
        self.yonetici_id = yonetici_id

    @discord.ui.button(label="✅ Kabul Et", style=discord.ButtonStyle.success, custom_id="kabul_btn")
    async def kabul(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Sadece takımın menajeri butona basabilir
        if interaction.user.id != self.yonetici_id:
            await interaction.response.send_message("❌ Bu teklife sadece takımın menajeri cevap verebilir!",
                                                    ephemeral=True)
            return

        # Bütçeleri matematiksel sayılara çevir
        alici_butce_int = sayiya_cevir(takimlar[self.alici_takim]["butce"])
        satici_butce_int = sayiya_cevir(takimlar[self.satici_takim]["butce"])
        teklif_int = sayiya_cevir(self.teklif_miktari)

        if alici_butce_int < teklif_int:
            await interaction.response.send_message("❌ Teklif yapan takımın kasasında yeterli para yok!",
                                                    ephemeral=True)
            return

        # PARALARI AKTAR (Alan takımdan düş, Satan takıma ekle)
        takimlar[self.alici_takim]["butce"] = butce_yaz(alici_butce_int - teklif_int)
        takimlar[self.satici_takim]["butce"] = butce_yaz(satici_butce_int + teklif_int)

        # Oyuncunun takımını kaydet
        if self.oyuncu_adi.lower() not in oyuncular:
            oyuncular[self.oyuncu_adi.lower()] = {"deger": "Bilinmiyor", "butce": "Bilinmiyor"}
        oyuncular[self.oyuncu_adi.lower()]["takim"] = self.alici_takim.title()

        veri_kaydet()

        # İşlem bitince butonları kapat
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content=f"🎉 **TRANSFER GERÇEKLEŞTİ!** 🎉\n**{self.oyuncu_adi.title()}**, {self.teklif_miktari} karşılığında **{self.alici_takim.title()}** takımına transfer oldu!\n*(Paralar kasalardan otomatik aktarıldı)*",
            view=self)

    @discord.ui.button(label="❌ Reddet", style=discord.ButtonStyle.danger, custom_id="red_btn")
    async def reddet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.yonetici_id:
            await interaction.response.send_message("❌ Bu teklife sadece takımın menajeri cevap verebilir!",
                                                    ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content=f"❌ **TRANSFER REDDEDİLDİ!**\n**{self.satici_takim.title()}** menajeri, **{self.oyuncu_adi.title()}** için yapılan teklifi geri çevirdi.",
            view=self)


# --- TAKIM KOMUTLARI ---

@bot.tree.command(name="takimekle", description="Sisteme yeni bir takım eklersiniz.")
@app_commands.describe(takim="Eklenecek takımın adı (Örn: Göztepe)",
                       yonetici="Takımın menajeri (Discord'dan birini etiketleyin)")
async def takimekle(interaction: discord.Interaction, takim: str, yonetici: discord.Member):
    takimlar[takim.lower()] = {"butce": "0 Euro", "yonetici_id": yonetici.id}
    veri_kaydet()
    await interaction.response.send_message(f"✅ **{takim.title()}** takımı lige eklendi! Menajeri: {yonetici.mention}")


@bot.tree.command(name="takimbutceekle", description="Bir takımın transfer bütçesini güncellersiniz.")
@app_commands.describe(takim="Takım adı", butce="Yeni bütçe (Örn: 50.000.000 Euro)")
async def takimbutceekle(interaction: discord.Interaction, takim: str, butce: str):
    if takim.lower() in takimlar:
        takimlar[takim.lower()]["butce"] = butce
        veri_kaydet()
        await interaction.response.send_message(
            f"💰 **{takim.title()}** takımının bütçesi **{butce}** olarak güncellendi!")
    else:
        await interaction.response.send_message("❌ Önce takımı eklemelisiniz! (Komut: `/takimekle`)")


@bot.tree.command(name="takimbutce", description="Tüm takımların veya tek bir takımın transfer bütçesini gösterir.")
@app_commands.describe(takim="Tek takım için adını yazın. Tüm liste için boş bırakın.")
async def takimbutce(interaction: discord.Interaction, takim: str = None):
    if takim:
        bilgi = takimlar.get(takim.lower())
        if bilgi:
            await interaction.response.send_message(
                f"🏦 **{takim.title()}** Takımının Transfer Bütçesi: **{bilgi.get('butce', 'Bilinmiyor')}**")
        else:
            await interaction.response.send_message("❌ Böyle bir takım bulunamadı.")
    else:
        if not takimlar:
            await interaction.response.send_message("📋 Sistemde henüz hiçbir takım yok.")
            return

        mesaj = "🏦 **TÜM TAKIMLARIN TRANSFER BÜTÇELERİ** 🏦\n\n"
        for ad, bilgi in takimlar.items():
            mesaj += f"• **{ad.title()}**: {bilgi.get('butce', 'Bilinmiyor')}\n"

        await interaction.response.send_message(mesaj)


# --- OYUNCU KOMUTLARI ---

@bot.tree.command(name="transferdegeriekle", description="Bir oyuncunun piyasa değerini eklersiniz.")
@app_commands.describe(oyuncu="Oyuncunun adı (Örn: Kylian Mbappe)", deger="Piyasa değeri (Örn: 25.000.000 Euro)")
async def transferdegeriekle(interaction: discord.Interaction, oyuncu: str, deger: str):
    if oyuncu.lower() not in oyuncular:
        oyuncular[oyuncu.lower()] = {"deger": deger, "butce": "Bilinmiyor", "takim": "Serbest"}
    else:
        oyuncular[oyuncu.lower()]["deger"] = deger
    veri_kaydet()
    await interaction.response.send_message(
        f"📈 **{oyuncu.title()}** adlı oyuncunun piyasa değeri **{deger}** olarak ayarlandı!")


@bot.tree.command(name="transferbutceekle", description="Bir oyuncuya özel bütçe tanımlarsınız.")
@app_commands.describe(oyuncu="Oyuncunun adı", butce="Oyuncunun bütçesi")
async def transferbutceekle(interaction: discord.Interaction, oyuncu: str, butce: str):
    if oyuncu.lower() not in oyuncular:
        oyuncular[oyuncu.lower()] = {"deger": "Bilinmiyor", "butce": butce, "takim": "Serbest"}
    else:
        oyuncular[oyuncu.lower()]["butce"] = butce
    veri_kaydet()
    await interaction.response.send_message(
        f"💼 **{oyuncu.title()}** adlı oyuncunun bütçesi **{butce}** olarak güncellendi!")


@bot.tree.command(name="transferdegeri", description="Tüm oyuncuların veya tek bir oyuncunun piyasa değerini gösterir.")
@app_commands.describe(oyuncu="Sadece bir oyuncuyu görmek istiyorsanız adını yazın. Tüm liste için boş bırakın.")
async def transferdegeri(interaction: discord.Interaction, oyuncu: str = None):
    if oyuncu:
        bilgi = oyuncular.get(oyuncu.lower())
        if bilgi:
            takim_metni = f"\n🏢 Takımı: **{bilgi.get('takim', 'Bilinmiyor')}**" if 'takim' in bilgi else ""
            await interaction.response.send_message(
                f"⚽ **{oyuncu.title()}**\n📉 Piyasa Değeri: **{bilgi['deger']}**\n💼 Bütçesi: **{bilgi['butce']}**{takim_metni}")
        else:
            await interaction.response.send_message("❌ Bu oyuncu sistemde bulunamadı.")
    else:
        if not oyuncular:
            await interaction.response.send_message("📋 Sistemde henüz hiçbir oyuncu yok.")
            return

        mesaj = "📋 **TÜM OYUNCULARIN PİYASA DEĞERLERİ** 📋\n"
        for ad, bilgi in oyuncular.items():
            mesaj += f"• [{ad.title()}] {bilgi['deger']} (Takımı: {bilgi.get('takim', 'Serbest')})\n"

        await interaction.response.send_message(mesaj)


@bot.tree.command(name="transferdegerikaldir", description="Bir oyuncuyu piyasa değeri listesinden tamamen siler.")
@app_commands.describe(oyuncu="Silinecek oyuncunun adı (Örn: Kylian Mbappe)")
async def transferdegerikaldir(interaction: discord.Interaction, oyuncu: str):
    if oyuncu.lower() in oyuncular:
        del oyuncular[oyuncu.lower()]
        veri_kaydet()
        await interaction.response.send_message(f"🗑️ **{oyuncu.title()}** adlı oyuncu sistemden kalıcı olarak silindi!")
    else:
        await interaction.response.send_message("❌ Bu oyuncu sistemde bulunamadı. Adını doğru yazdığına emin ol.")


@bot.tree.command(name="transferteklifi", description="Başka bir takıma oyuncu transferi için teklif gönderir.")
@app_commands.describe(hedef_takim="Teklif yapılacak takım (Örn: Kasımpaşa)", oyuncu="İstenen oyuncunun adı",
                       teklif="Teklif edilen miktar (Örn: 15.000.000 Euro)")
async def transferteklifi(interaction: discord.Interaction, hedef_takim: str, oyuncu: str, teklif: str):
    # Teklifi kimin (hangi takımın) yaptığını Discord ID'sinden bulalım
    teklif_yapan_takim = None
    for t_ad, t_bilgi in takimlar.items():
        if type(t_bilgi) == dict and t_bilgi.get("yonetici_id") == interaction.user.id:
            teklif_yapan_takim = t_ad
            break

    if not teklif_yapan_takim:
        await interaction.response.send_message(
            "❌ Sistemde yöneticisi olduğunuz bir takım bulunamadı! İşlem yapabilmek için bir takımın menajeri olmalısınız.",
            ephemeral=True)
        return

    hedef = hedef_takim.lower()
    if hedef not in takimlar:
        await interaction.response.send_message(f"❌ **{hedef_takim.title()}** adında bir takım bulunamadı.",
                                                ephemeral=True)
        return

    hedef_yonetici_id = takimlar[hedef].get("yonetici_id")
    if not hedef_yonetici_id:
        await interaction.response.send_message(
            f"❌ **{hedef_takim.title()}** takımının henüz bir menajeri (Discord kullanıcısı) yok! Teklif iletilemiyor.",
            ephemeral=True)
        return

    if teklif_yapan_takim == hedef:
        await interaction.response.send_message("❌ Kendi kendinize teklif yapamazsınız!", ephemeral=True)
        return

    # Teklif butonlarını oluştur
    view = TransferView(alici_takim=teklif_yapan_takim, satici_takim=hedef, teklif_miktari=teklif, oyuncu_adi=oyuncu,
                        yonetici_id=hedef_yonetici_id)

    mesaj = f"🔔 <@{hedef_yonetici_id}>, takımına transfer teklifi var!\n\n" \
            f"🏢 **Teklifi Yapan:** {teklif_yapan_takim.title()}\n" \
            f"⚽ **İstenen Oyuncu:** {oyuncu.title()}\n" \
            f"💰 **Teklif Edilen Miktar:** {teklif}"

    await interaction.response.send_message(mesaj, view=view)


# DİKKAT: YENİ TOKEN'INI BURAYA YAPIŞTIR
bot.run('MTU2MDk1NDQ5OTExMDAxNTAxNg.GMHiAv.AubrZIWLxFfVHi5wNe0j8XmVj1WKzK4NcmO4KE')