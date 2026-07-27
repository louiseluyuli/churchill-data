import json
import requests

url = "https://api.gbif.org/v1/occurrence/search"

params = {
    "decimalLatitude": "58,60",
    "decimalLongitude": "-96,-92",
    "hasCoordinate": "true",
    "limit": 5,
}

response = requests.get(url, params=params, timeout=30)
response.raise_for_status()

data = response.json()

with open("gbif_test.json", "w", encoding="utf-8") as file:
    json.dump(data, file, ensure_ascii=False, indent=2)

print("匹配记录总数：", data.get("count"))

for record in data.get("results", []):
    print(
        record.get("scientificName"),
        "|", record.get("kingdom"),
        "|", record.get("order"),
        "|", record.get("family"),
    )

print("测试数据已保存到 gbif_test.json")
