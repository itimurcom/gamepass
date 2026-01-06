# Опис Sigl ID з каталогу Xbox Game Pass

**Джерело:** [https://www.xbox.com/en-MY/xbox-game-pass/games/js/xgpcatPopulate-MWF2.js](https://www.xbox.com/en-MY/xbox-game-pass/games/js/xgpcatPopulate-MWF2.js)

Цей документ містить перелік ідентифікаторів (**Sigl ID**), які використовуються для запитів до API `https://catalog.gamepass.com/sigls/v2` для формування динамічних списків ігор.

---

## 1. Основні та Глобальні колекції
Ці ідентифікатори відповідають за великі блоки ігор та статус їх перебування в каталозі.

| Назва (Key) | Sigl ID | Опис / Платформа |
| :--- | :--- | :--- |
| **pcgaVTaz** | `609d944c-d395-4c0a-9ea4-e9f39b52c1ad` | Усі ігри PC Game Pass (від A до Z) |
| **pcgaVTpopular** | `a884932a-f02b-40c8-a903-a008c23b1df1` | Найпопулярніші ігри на ПК |
| **XGPPMPRecentlyAdded** | `3fdd7f57-7092-4b65-bd40-5a9dac1b2b84` | Нещодавно додані ігри |
| **pccomingsoon** | `4165f752-d702-49c8-886b-fb57936f6bae` | Ігри, що з'являться в каталозі незабаром |
| **SubsXGPLeavingSoon** | `cc7fc951-d00f-410e-9e02-5e4628e04163` | Останній шанс (ігри, що скоро залишать підписку) |
| **pdoPC** | `4b59700c-801f-494a-a34c-842b8c98f154` | Play Day One (Доступні з дня світового релізу) |
| **allCloud** | `29a81209-df6f-41fd-a528-2ae6b91f719c` | Повний каталог Cloud Gaming |
| **popCloud** | `e7590b22-e299-44db-ae22-25c61405454c` | Найпопулярніші хмарні ігри |
| **touchCloud** | `e7590b22-e299-44db-ae22-25c61405454c` | Ігри з підтримкою сенсорного керування |

---

## 2. Категорії Видавців та Партнерів
Спеціалізовані підканали ігор від конкретних студій або за спеціальними програмами.

| Назва (Key) | Sigl ID | Опис контенту |
| :--- | :--- | :--- |
| **eaplayPC** | `1d33fbb9-b895-4732-a8ca-a55c8b99fa2c` | Каталог ігор EA Play для персональних комп'ютерів |
| **bethpc** | `79fe89cf-f6a3-48d4-af6c-de4482cf4a51` | Ігри видавництва Bethesda Softworks |
| **riotgamespc** | `7008e21d-2b70-4fab-b6dc-a220ebae001f` | Колекція ігор від Riot Games |
| **ftpbenefitspc** | `3a6b073e-9719-4071-b7a3-6d836f5d949e` | Free-to-play ігри з бонусами для підписників |

---

## 3. Жанрові та Тематичні списки
Використовуються для фільтрації каталогу за ігровими жанрами.

| Назва (Key) | Sigl ID | Жанрова приналежність |
| :--- | :--- | :--- |
| **pcgaVTIndies** | `1e2ce757-e84f-4d2c-9243-34b81912644a` | Незалежні розробники (Indies) |
| **pcgaVTRPG** | `c621daed-3d22-4745-afc9-19ed77a2e9be` | Рольові ігри (RPG) |
| **pcgaVTStrategy** | `7a3b01ac-93e4-4d52-81ad-980bc4cb4ff5` | Стратегічні ігри |
| **pcgaVTFamily** | `0f0bccc0-cdc8-4e1a-bfca-4b7da5c6c418` | Ігри для всієї родини |
| **pcgaVTSimulation** | `f0e9ffe0-176e-41af-be11-c40a05d26e2c` | Симулятори |
| **XGPPMPActionAdventure** | `0f4967a6-7226-48bd-8ab4-a6ef40b09981` | Екшн та Пригоди |
| **XGPPMPShooters** | `590d891f-0f12-4bd6-8d58-28c5d612ba38` | Шутери |
| **sportsPC** | `6661f37d-6159-4c9c-81d8-668af0a78b04` | Спортивні ігри |
| **XGPPMPIDXbox** | `4c894453-744d-4b35-acea-40df9f4312b1` | ID@Xbox (Інді-колекція для консолей) |
| **XGPPMPFamilyFriendly** | `8e5089f1-5947-4ce1-9db1-94644556e493` | Підбірка для всієї родини |

---

## 4. Списки для Cloud & Mobile
Колекції, що оптимізовані для гри через хмару на різних пристроях.

| Назва (Key) | Sigl ID | Особливість доступу |
| :--- | :--- | :--- |
| **mobileCloud** | `88c10a22-33b5-4e24-90b6-125bee02da39` | Оптимізовано для мобільних пристроїв |
| **aaCloud** | `ebedc400-a688-4929-b794-4435b2e1ab0a` | Пригоди в хмарі (Action/Adventure Cloud) |
| **famCloud** | `f576ca76-9aad-4ac7-a0f0-71429ef36850` | Сімейні ігри через хмару |
| **fightCloud** | `c4be032d-0f42-4df5-8934-1758748cf7f0` | Файтинги (Cloud) |
| **indieCloud** | `95f39cf3-48ec-4d3c-83e6-a7f6916fbdfe` | Інді-ігри (Cloud) |
| **rpgCloud** | `e68225ce-e42f-4156-998d-697bf985da73` | RPG (Cloud) |
| **shooterCloud** | `38441e3f-26c6-498c-8b84-0ca20a3785af` | Шутери (Cloud) |
| **simCloud** | `200674bd-7bd4-4360-bd0f-af8cd899839f` | Симулятори (Cloud) |
| **stratCloud** | `5d6c2384-b30e-4717-86f6-e684e819622b` | Стратегії (Cloud) |

---

## 5. Додаткові технічні ID (xgpGuidArray)
Ці ідентифікатори присутні в коді як системні або допоміжні:

* `a884932a-f02b-40c8-a903-a008c23b1df1`
* `29a81209-df6f-41fd-a528-2ae6b91f719c`
* `5d6c2384-b30e-4717-86f6-e684e819622b`
* `ebedc400-a688-4929-b794-4435b2e1ab0a`
* `f576ca76-9aad-4ac7-a0f0-71429ef36850`
* `c4be032d-0f42-4df5-8934-1758748cf7f0`
* `95f39cf3-48ec-4d3c-83e6-a7f6916fbdfe`
* `e68225ce-e42f-4156-998d-697bf985da73`
* `38441e3f-26c6-498c-8b84-0ca20a3785af`
* `200674bd-7bd4-4360-bd0f-af8cd899839f`

---

### Шаблон використання (API Request):
Для отримання JSON списку ігор використовуйте таку структуру посилання:
`https://catalog.gamepass.com/sigls/v2?id=ВАШ_SIGL_ID&language=uk-ua&market=UA`

---
**Примітка:** Ці дані відповідають версії API v2.