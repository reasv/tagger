from typing import Union

from sqlalchemy import CTE

from panoptikon.db.pql.filters.bookmarks import InBookmarks, InBookmarksArgs
from panoptikon.db.pql.filters.extracted_text import MatchText, MatchTextArgs
from panoptikon.db.pql.filters.path_in import InPaths
from panoptikon.db.pql.filters.path_text import MatchPath, MatchPathArgs
from panoptikon.db.pql.filters.type_in import TypeIn
from panoptikon.db.pql.types import Filter
from panoptikon.db.pql.utils import QueryState

Filters = Union[InPaths, InBookmarks, TypeIn, MatchPath, MatchText]


def filter_function(filter: Filter, context: CTE, state: QueryState) -> CTE:
    if isinstance(filter, Filter):
        query = filter.build_query(context)
    else:
        raise ValueError(f"Unknown filter type: {filter.__class__.__name__}")
    filter_type = filter.__class__.__name__
    cte_name = f"n_{state.cte_counter}_{filter_type}"
    state.cte_counter += 1
    return query.cte(cte_name)
