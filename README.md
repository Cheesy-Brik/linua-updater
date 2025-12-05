# Linua Updater

A lightweight and efficient updater for The Sims 4 DLC content.

## Features
- **Easy DLC Installation**: Simple one-click installation of Expansion Packs, Game Packs, Stuff Packs, and Free Packs
- **Automatic Game Detection**: Automatically finds your Sims 4 installation folder
- **Safe & Secure**: Only downloads from verified sources
- **Progress Tracking**: Real-time download and installation progress
- **Repair System**: Built-in game file verification and repair
- **Dark Theme**: Easy on the eyes interface

## System Requirements
- Windows 10 or later
- The Sims 4 installed
- 10GB free disk space (for large DLC installations)
- Internet connection

## How to Use
1. Download the latest `Linua-Updater.exe` from the Releases page
2. Run the executable (no installation required)
3. Select your Sims 4 folder (usually auto-detected)
4. Choose which DLC you want to install
5. Click Update and wait for installation to complete

## 🇷🇺 Для пользователей из России / For Russian users

**Известная проблема**: EP03 "City Living" и EP06 "Get Famous" могут не скачиваться через программу из-за блокировок в РФ.

### 🔧 Решение: Полностью ручная установка EP03 и EP06

#### 📥 1. Скачайте архивы вручную:
- **EP03 - City Living (2.6 GB):** https://gofile.io/d/7zzJA5  
  *(Если не открывается — включите VPN)*
- **EP06 - Get Famous (2.6 GB):** https://gofile.io/d/PJ6wc4  
  *(Если не открывается — включите VPN)*

#### 🛠️ 2. Распакуйте архивы:
1. Убедитесь что у вас есть **WinRAR** или **7-Zip**
2. Распакуйте оба архива — в каждом будут **две папки**:
EP03/
_Installer/

#### 📂 3. Установите вручную в корень The Sims 4:
1. Найдите папку **The Sims 4** (обычно):
- `C:\Program Files (x86)\Steam\steamapps\common\The Sims 4`
- или где у вас установлена игра

2. **Скопируйте обе папки** из распакованного архива в корень The Sims 4:
- Папку `EP03` → в `The Sims 4\`
- Папку `_Installer` → в `The Sims 4\`

3. **Если Windows спрашивает "Заменить файлы?"** — нажмите **"Заменить файлы в папке назначения"**

4. **Повторите для EP06** — скопируйте его `EP06` и `_Installer` (файлы заменятся автоматически)

#### ✅ **Правильная структура после установки:**
The Sims 4
├── EP03
├── EP06
├── _Installer\ (общий для всех DLC)
├── Game
├── Data
└── ... другие папки

#### 🎮 5. Запустите Linua Updater для остальных DLC:
1. Запустите **Linua Updater**
2. **НЕ выбирайте EP03 и EP06** (они уже установлены вручную)
3. Выберите остальные нужные DLC
4. Нажмите **"Update"** — программа установит все кроме EP03/EP06

#### 🎥 **Видеоинструкция по распаковке:**
📺 **Смотрите с 3:00 минуты:** https://www.youtube.com/watch?v=6UonIuoSpOY&t=11s

---

**Важно!** EP03 и EP06 устанавливаются **ТОЛЬКО ВРУЧНУЮ**. Программа их не установит из-за блокировок.

## Supported DLC
### Expansion Packs
- Get to Work (EP01)
- Get Together (EP02)
- City Living (EP03) — *только ручная установка для РФ*
- Cats and Dogs (EP04)
- Seasons (EP05)
- Get Famous (EP06) — *только ручная установка для РФ*
- Island Living (EP07)
- Discover University (EP08)
- Eco Lifestyle (EP09)
- Snowy Escape (EP10)
- Cottage Living (EP11)
- High School Years (EP12)
- Growing Together (EP13)
- Horse Ranch (EP14)
- For Rent (EP15)
- Lovestruck (EP16)

### Game Packs
- Outdoor Retreat (GP01)
- Spa Day (GP02)
- Dine Out (GP03)
- Vampires (GP04)
- Parenthood (GP05)
- Jungle Adventure (GP06)
- StrangerVille (GP07)
- Realm of Magic (GP08)
- Star Wars: Journey to Batuu (GP09)
- Dream Home Decorator (GP10)
- My Wedding Stories (GP11)
- Werewolves (GP12)

### Stuff Packs
- Luxury Party Stuff (SP01)
- Perfect Patio Stuff (SP02)
- Cool Kitchen Stuff (SP03)
- Spooky Stuff (SP04)
- Movie Hangout Stuff (SP05)
- Romantic Garden Stuff (SP06)
- Kids Room Stuff (SP07)
- Backyard Stuff (SP08)
- Vintage Glamour Stuff (SP09)
- Bowling Night Stuff (SP10)
- Fitness Stuff (SP11)
- Toddler Stuff (SP12)
- Laundry Day Stuff (SP13)
- My First Pet Stuff (SP14)
- Moschino Stuff (SP15)
- Tiny Living Stuff (SP16)
- Nifty Knitting (SP17)
- Paranormal Stuff (SP18)

### Free Packs
- Holiday Celebration Pack (FP01)

## Troubleshooting
### Common Issues
**EP03/EP06 не устанавливаются через программу (для РФ)**:
- Это нормально! Следуйте инструкции "Для пользователей из России" выше
- Устанавливайте EP03/EP06 вручную (2 папки в корень игры)
- Остальные DLC установятся через программу

**Game not detected automatically**:
- Use the "Browse" button to manually select your Sims 4 folder
- Typical locations:
  - `C:\Program Files (x86)\Steam\steamapps\common\The Sims 4`
  - `C:\Program Files\EA Games\The Sims 4`
  - `C:\Program Files (x86)\Origin Games\The Sims 4`

**Installation fails**:
- Check your internet connection
- Ensure you have enough disk space (at least 10GB free)
- Run as Administrator if experiencing permission issues
- Temporarily disable antivirus if it blocks the download

**DLC not appearing in game**:
- Use the "Repair" function to verify game files
- Ensure the DLC folders are in your main Sims 4 directory
- Restart the game after installation

## Safety Notice
⚠️ **Important**: This software is completely free. If you paid for it, you were scammed.

The only legitimate sources for this program are:
- Official GitHub repository: `l1ntol/linua-updater`
- Official releases page

**Do not download from any other sources.**

## 🛡️ Security & False Positives / Безопасность и ложные срабатывания

### Fake versions with viruses / Подделки с вирусами
Scammers steal the updater, add viruses and distribute fake versions.

### Antivirus false positives / Ложные срабатывания антивирусов
All pirated software is detected as "threats". This is normal:
- Anadius Unlocker → "virus"
- ZloEmu → "virus"  
- Our updater → "virus"

### How to verify safety / Как проверить безопасность
1. Download source code from GitHub
2. Check it (1100 lines, nothing hidden)
3. Run in sandbox if unsure

### Original vs Fake / Оригинал vs Подделка
- ✅ Original: open source, no hidden processes
- ❌ Fake: closed source, hidden processes, background downloads

## Technical Information
- Version: 2.0
- Platform: Windows
- Architecture: x64
- Requirements: .NET Framework 4.8 (usually pre-installed on Windows 10/11)

## Support
Если у вас проблемы с EP03/EP06:
1. **Прочитайте раздел "Для пользователей из России" выше**
2. Следуйте инструкциям по ручной установке
3. Убедитесь что скопировали **обе папки** в **корень игры**

**Внимание:** Issues про EP03/EP06 без попытки ручной установки будут закрываться!

## Legal
This project is not affiliated with or endorsed by Electronic Arts (EA) or Maxis. The Sims 4 is a registered trademark of Electronic Arts Inc. This software is intended for educational purposes and personal use only.
