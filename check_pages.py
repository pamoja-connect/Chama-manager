import re, sys
from app import app
import routes  # registers all pages
from models import User

SKIP = re.compile(r'logout|delete|remove|toggle|approve|reject|reset|clear|send|backup|export|download|static|sw\.js|offline', re.I)
app.config['PROPAGATE_EXCEPTIONS'] = True

for name in sys.argv[1:]:
    with app.app_context():
        u = User.query.filter_by(username=name).first()
        uid = u.id if u else None
    if uid is None:
        print('No such user:', name); continue
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(uid)
        s['_fresh'] = True
    total = bad = 0
    for rule in app.url_map.iter_rules():
        if 'GET' not in rule.methods or SKIP.search(rule.rule + rule.endpoint):
            continue
        url = re.sub(r'<[^>]+>', '1', rule.rule)
        total += 1
        try:
            code = c.get(url).status_code
            if code >= 500:
                bad += 1; print('500 ', url)
        except Exception as e:
            bad += 1
            print('ERR ', url, '->', type(e).__name__ + ':', str(e)[:120].replace('\n', ' '))
    print('==', name, '| pages checked:', total, '| problems:', bad)
