"""Public collection plan: data only, never credentials or executable commands."""
import re

def validate_plan(value):
    if not isinstance(value, dict) or value.get('schemaVersion') != 1:
        raise ValueError('수집 설정 형식을 확인하세요.')
    if type(value.get('enabled')) is not bool or type(value.get('intervalHours')) is not int or value['intervalHours'] not in (1, 3, 6):
        raise ValueError('수집 간격은 1·3·6시간 중 선택하세요.')
    targets = value.get('targets')
    if not isinstance(targets, list) or not 1 <= len(targets) <= 3:
        raise ValueError('단지는 1~3개 등록할 수 있습니다.')
    seen = set(); clean = []
    for row in targets:
        if not isinstance(row, dict): raise ValueError('단지 형식 오류')
        number = row.get('complexNo')
        if not isinstance(number, str) or not re.fullmatch(r'[1-9][0-9]{0,11}', number) or number in seen:
            raise ValueError('중복 없는 숫자 단지 번호를 입력하세요.')
        label = row.get('label', '')
        if not isinstance(label, str) or len(label) > 60 or any(ord(c) < 32 for c in label):
            raise ValueError('단지 별칭은 60자 이내로 입력하세요.')
        seen.add(number); clean.append(dict(complexNo=number, label=label.strip()))
    return dict(schemaVersion=1, enabled=value['enabled'], intervalHours=value['intervalHours'], targets=clean)
