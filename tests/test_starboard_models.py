import unittest
from starboard.models import normalize,eligible,emoji,voter_count


class StarboardRulesTests(unittest.TestCase):
    def board(self,**values):return normalize({'name':'Generated board','target_channel_id':'20','source_channel_ids':['10'],**values})

    def test_sources_are_explicit_bounded_and_do_not_include_the_target(self):
        self.assertEqual(self.board()['source_channel_ids'],[10])
        for values in ({'source_channel_ids':[]},{'source_channel_ids':[20]}, {'source_channel_ids':[True]}, {'excluded_channel_ids':[10]}, {'threshold':True},{'threshold':101},{'retention_days':0}):
            with self.subTest(values=values),self.assertRaises(ValueError):self.board(**values)

    def test_thread_parent_inclusion_and_either_level_exclusion(self):
        source={'channel_id':11,'parent_channel_id':10,'author_bot':False}
        self.assertTrue(eligible(self.board(),source))
        self.assertFalse(eligible(self.board(excluded_channel_ids=[11]),source))
        self.assertFalse(eligible(self.board(source_channel_ids=[11],excluded_channel_ids=[10]),source))
        for key in ('author_bot','deleted','nsfw'):
            self.assertFalse(eligible(self.board(),{**source,key:True}))
        self.assertFalse(eligible(self.board(),{**source,'channel_id':20}))

    def test_custom_and_unicode_reaction_normalization(self):
        self.assertEqual(emoji('<a:star:123>'),'custom:123')
        self.assertEqual(emoji('<:renamed:123>'),emoji('custom:123'))
        self.assertEqual(emoji('⭐\ufe0f'),emoji('⭐'))
        for value in ('','words','line\nbreak','⭐words','⭐⭐',False):
            with self.assertRaises(ValueError):emoji(value)

    def test_unique_people_exclude_bots_author_and_bounded_overflow(self):
        values=[{'id':1,'bot':False},{'id':2,'bot':False},{'id':2,'bot':False},{'id':3,'bot':True}]
        self.assertEqual(voter_count(values,1),1)
        with self.assertRaises(ValueError):voter_count(values*1251,1)
