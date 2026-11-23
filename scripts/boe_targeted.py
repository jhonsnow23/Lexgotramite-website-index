"""Compatibility bridge for existing v4.4 source-grounded generator.
Do not equate successful extraction or quotations with legal correctness.
"""
try:
    from boe_universal_v45 import retrieve, BOEError
except ImportError:
    from scripts.boe_universal_v45 import retrieve, BOEError


def retrieve_articles(doc_id, numbers, *, opener=None, max_total=26000):
    kwargs={'max_context':max_total}
    if opener is not None:kwargs['opener']=opener
    return retrieve(doc_id,numbers,**kwargs)
