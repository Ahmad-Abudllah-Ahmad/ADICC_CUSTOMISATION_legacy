"""‌⁠‍Replace the personal 'I read every message myself' form_title with a
   neutral, less first-person version, in en/de/ru."""
import json
from pathlib import Path

BASE = Path('C:/Users/Artem Boiko/Desktop/CodeProjects/ERP_26030500/website-marketing/pro/breeze/locales')

NEW_TITLES = {
    'en': "Tell us what you\u2019re after. <em>Every message gets a real reply.</em>",
    'de': "Sagen Sie uns, worum es Ihnen geht. <em>Jede Nachricht bekommt eine echte Antwort.</em>",
    'ru': "Расскажите, что вам нужно. <em>На каждое сообщение приходит реальный ответ.</em>",
}

for lang, new_title in NEW_TITLES.items():
    p = BASE / f'{lang}.json'
    data = json.loads(p.read_text(encoding='utf-8'))
    old = data['custom']['form_title']
    data['custom']['form_title'] = new_title
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{lang}: OLD = {old}')
    print(f'{lang}: NEW = {new_title}\n')
