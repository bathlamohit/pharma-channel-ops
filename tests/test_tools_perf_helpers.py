"""The speed helpers in agent/tools.py must give exactly what the slow pandas forms gave."""
import pandas as pd
import pytest

from agent.tools import group_lists, stock_on_hand, table


@pytest.mark.parametrize("sort", [True, False])
def test_group_lists_matches_agg_list_on_sales(sort):
    s = table("primary_sales.csv")
    by = ["invoice_no", "sku_code"]
    assert group_lists(s, by, "src_line", sort=sort) == s.groupby(by, sort=sort)["src_line"].agg(list).tolist()


def test_group_lists_small_and_empty():
    df = pd.DataFrame({"k": ["b", "a", "b", "a", "c"], "v": [1, 2, 3, 4, 5]})
    assert group_lists(df, ["k"], "v") == [[2, 4], [1, 3], [5]]
    assert group_lists(df, ["k"], "v", sort=False) == [[1, 3], [2, 4], [5]]
    assert group_lists(df.iloc[0:0], ["k"], "v") == []


def test_stock_on_hand_matches_per_group_sum():
    st = table("cnf_stock_snapshot.csv")
    for day in st["snapshot_date"].unique()[-3:]:
        old = st[st["snapshot_date"] == day].groupby(["cnf_code", "sku_code"])["qty_on_hand_packs"].apply(
            lambda x: x.astype(float).sum())
        pd.testing.assert_series_equal(stock_on_hand(day), old, check_names=False)


def test_stock_on_hand_returns_a_copy():
    day = table("cnf_stock_snapshot.csv")["snapshot_date"].max()
    a = stock_on_hand(day)
    a.iloc[0] = -1
    assert stock_on_hand(day).iloc[0] != -1
