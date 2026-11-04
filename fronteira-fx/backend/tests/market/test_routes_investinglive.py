"""Rotas /v1/market/news e /v1/market/sentiment: trecho curto só onde o feed autoriza, atribuição em todo item,
guid fora da API e leitura de sentimento sempre não executável."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fronteira_fx.models import NewsItem, SentimentReading

CAPTURED = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def test_routes_show_excerpt_and_attribution_on_every_item(client, db):
    db.add(
        NewsItem(
            source="investinglive",
            feed="investinglive",
            title="Exemplo: PMI de serviços",
            link="https://investinglive.com/news/exemplo/",
            guid="g-api",
            excerpt="Anterior 51,7.",
            published_at=CAPTURED,
            captured_at=CAPTURED,
            data_mode="real",
        )
    )
    db.add(
        NewsItem(
            source="infomoney",
            feed="infomoney",
            title="Manchete sem trecho",
            link="https://exemplo.com/sem-trecho",
            published_at=CAPTURED - timedelta(hours=1),
            captured_at=CAPTURED,
            data_mode="real",
        )
    )
    db.add(
        SentimentReading(
            index_id="fng",
            provider="alternative.me",
            value=34,
            classification="Fear",
            observed_at=CAPTURED.replace(hour=0),
            captured_at=CAPTURED,
            data_mode="real",
        )
    )
    db.commit()
    news = client.get("/v1/market/news").json()
    by_source = {n["source"]: n for n in news}
    assert by_source["investinglive"]["excerpt"] == "Anterior 51,7."
    assert "Investinglive.com" in by_source["investinglive"]["attribution"]
    assert by_source["infomoney"]["excerpt"] is None
    assert by_source["infomoney"]["attribution"] == "Fonte: InfoMoney"
    assert all(n["attribution"] for n in news)
    assert "guid" not in by_source["investinglive"]  # guid é só dedupe, não sai na API

    sentiment = client.get("/v1/market/sentiment").json()
    assert len(sentiment) == 1
    assert sentiment[0]["value"] == 34 and sentiment[0]["executable"] is False
    assert "Alternative.me" in sentiment[0]["attribution"]
    assert client.get("/v1/market/sentiment", params={"limit": 91}).status_code == 422
