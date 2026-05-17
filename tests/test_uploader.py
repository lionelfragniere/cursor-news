from cursor_news.uploader import _url_with_metadata


def test_url_with_metadata_replaces_existing_data_query():
    url = _url_with_metadata("https://api.example.test/metadata?data=old&keep=1", "Cursor News - Pote")
    assert url == "https://api.example.test/metadata?keep=1&data=Cursor+News+-+Pote"
