"""Pure board configuration and message eligibility; no Discord SDK dependencies."""
import re
import unicodedata
from discord_io.emoji import is_unicode_emoji


def integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'invalid_{name}')
    return value


def snowflake(value, name):
    if isinstance(value,str) and value.isascii() and value.isdigit():value=int(value)
    return integer(value,name,1,2**63-1)


def ids(values, name, *, required=False):
    if not isinstance(values,list) or len(values)>25:
        raise ValueError(f'invalid_{name}')
    result=list(dict.fromkeys(snowflake(v,name) for v in values))
    if required and not result:raise ValueError(f'invalid_{name}')
    return result


def emoji(value):
    if not isinstance(value,str):raise ValueError('invalid_emoji')
    value=value.strip()
    custom=re.fullmatch(r'(?:<a?:[^:<>]{1,32}:([0-9]+)>|custom:([0-9]+))',value)
    if custom:return 'custom:'+str(snowflake(custom.group(1) or custom.group(2),'emoji'))
    # Variation selectors affect presentation, not which reaction is counted.
    value=unicodedata.normalize('NFC',value).replace('\ufe0f','')
    if not 1<=len(value)<=32 or any(c.isspace() or ord(c)<32 for c in value):raise ValueError('invalid_emoji')
    if not is_unicode_emoji(value):raise ValueError('invalid_emoji')
    return value


def normalize(values):
    if not isinstance(values,dict):raise ValueError('invalid_board')
    name=values.get('name','')
    if not isinstance(name,str) or not 1<=len(name.strip())<=80 or any(ord(c)<32 for c in name):raise ValueError('invalid_name')
    enabled=values.get('enabled',False)
    if type(enabled) is not bool:raise ValueError('invalid_enabled')
    target=snowflake(values.get('target_channel_id'),'target_channel_id')
    sources=ids(values.get('source_channel_ids',[]),'source_channel_ids',required=True)
    excluded=ids(values.get('excluded_channel_ids',[]),'excluded_channel_ids')
    if target in sources:raise ValueError('target_is_source')
    if not set(sources)-set(excluded):raise ValueError('all_sources_excluded')
    return {'name':name.strip(),'enabled':enabled,'target_channel_id':target,'source_channel_ids':sources,
            'excluded_channel_ids':excluded,'emoji':emoji(values.get('emoji','⭐')),
            'threshold':integer(values.get('threshold',3),'threshold',1,100),
            'retention_days':integer(values.get('retention_days',30),'retention_days',1,365)}


def eligible(config, source):
    """Explicit parent channels include threads; either level can be excluded."""
    if source.get('author_bot') or source.get('deleted') or source.get('nsfw'):return False
    channel=source['channel_id'];parent=source.get('parent_channel_id')
    excluded=set(config['excluded_channel_ids'])
    return (channel!=config['target_channel_id'] and channel not in excluded and parent not in excluded
            and bool({channel,parent}&set(config['source_channel_ids'])))


def voter_count(voters, author_id):
    """An exact bounded result: overflow is rejected rather than undercounted."""
    if len(voters)>5000:raise ValueError('reaction_user_limit')
    return len({v['id'] for v in voters if v['id']!=author_id and not v['bot']})
