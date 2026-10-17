"""Pure taxonomy, label and canonical-merge rules for the Suggestions roadmap."""
from .models import SuggestionValidationError


def label(value, path):
    if not isinstance(value,str):
        raise SuggestionValidationError(path,'名前を文字列で指定してください。')
    value=value.strip()
    if not 1 <= len(value) <= 40 or any(ord(c)<32 or ord(c)==127 for c in value):
        raise SuggestionValidationError(path,'名前は改行を含まない1〜40文字で指定してください。')
    return value


def taxonomy(values, path, maximum):
    if not isinstance(values,list) or len(values)>maximum:
        raise SuggestionValidationError(path,f'選択肢は{maximum}件以内の一覧で指定してください。')
    result=[];seen=set()
    for index,value in enumerate(values):
        value=label(value,f'{path}.{index}')
        if value.casefold() in seen:
            raise SuggestionValidationError(path,'同じ名前の選択肢を重複して登録できません。')
        seen.add(value.casefold());result.append(value)
    return result


def labels(category, tags, settings):
    categories={value.casefold():value for value in taxonomy(settings.get('categories',[]),'categories',20)}
    available={value.casefold():value for value in taxonomy(settings.get('tags',[]),'tags',50)}
    if not isinstance(category,str):
        raise SuggestionValidationError('category','カテゴリーを選択してください。')
    category=category.strip()
    if category:
        category=categories.get(category.casefold())
        if category is None:
            raise SuggestionValidationError('category','登録済みのカテゴリーを選択してください。')
    clean=taxonomy(tags,'tags',10)
    if any(value.casefold() not in available for value in clean):
        raise SuggestionValidationError('tags','登録済みのタグを選択してください。')
    return {'category':category,'tags':[available[value.casefold()] for value in clean]}


def merge(source,target,reason,source_revision,target_revision,now):
    """The Repository holds the Guild/row locks before applying these rules."""
    if source['guild_id']!=target['guild_id']:
        raise PermissionError('merge_guild_mismatch')
    if source['id']==target['id']:
        raise ValueError('merge_self')
    if any(row.get('expires_at') is not None and row['expires_at']<=now for row in (source,target)):
        raise LookupError('suggestion_expired')
    if (type(source_revision) is not int or type(target_revision) is not int
            or source['revision']!=source_revision or target['revision']!=target_revision):
        raise RuntimeError('revision_conflict')
    if source.get('merged_into') is not None or target.get('merged_into') is not None:
        raise RuntimeError('canonical_suggestion_required')
    if target['status']=='delivery_failed' or source['status']=='merged' or target['status']=='merged':
        raise RuntimeError('suggestion_not_mergeable')
    if not isinstance(reason,str) or not 1 <= len(reason.strip()) <= 1000:
        raise ValueError('invalid_merge_reason')
    return reason.strip()
