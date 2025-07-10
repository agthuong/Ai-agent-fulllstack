from tavily import TavilyClient
client = TavilyClient("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")
response = client.search(
    query="giá vàng"
)
print(response)