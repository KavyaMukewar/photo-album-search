# v3
import json, os, re, base64, uuid, urllib.request, urllib.parse, urllib.error
import boto3
from botocore.config import Config

lex = boto3.client("lexv2-runtime")
s3 = boto3.client("s3", region_name="us-east-1",
                  config=Config(signature_version="s3v4"))

ES_HOST = os.environ["ES_HOST"].rstrip("/")
ES_USER = os.environ["ES_USER"]
ES_PASS = os.environ["ES_PASS"]
BOT_ID = os.environ["BOT_ID"]
BOT_ALIAS_ID = os.environ.get("BOT_ALIAS_ID", "TSTALIASID")
LOCALE_ID = os.environ.get("LOCALE_ID", "en_US")
INDEX = "photos"

STOPWORDS = {"show", "me", "photos", "photo", "pictures", "picture", "pics",
             "images", "image", "with", "and", "or", "of", "in", "them", "the",
             "a", "an", "find", "search", "for", "some", "please", "get", "i",
             "want", "to", "see", "that", "have", "has", "containing", "all"}
IRREGULAR = {"people": "person", "men": "man", "women": "woman",
             "children": "child", "mice": "mouse", "geese": "goose",
             "feet": "foot", "teeth": "tooth"}

CORS = {"Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "GET,PUT,OPTIONS"}


def es_request(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(ES_HOST + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    token = base64.b64encode(f"{ES_USER}:{ES_PASS}".encode()).decode()
    req.add_header("Authorization", "Basic " + token)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def words(text):
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS]


def variants(w):
    v = {w}
    if w in IRREGULAR:
        v.add(IRREGULAR[w])
    if w.endswith("ies") and len(w) > 4:
        v.add(w[:-3] + "y")
    elif w.endswith(("ses", "xes", "ches", "shes")):
        v.add(w[:-2])
    elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        v.add(w[:-1])
    v.add(w + "s")
    return v


def lex_keywords(q):
    try:
        resp = lex.recognize_text(botId=BOT_ID, botAliasId=BOT_ALIAS_ID,
                                  localeId=LOCALE_ID, sessionId=str(uuid.uuid4()),
                                  text=q)
        intent = resp.get("sessionState", {}).get("intent", {})
        print("Lex intent:", json.dumps(intent))
        if intent.get("name") != "SearchIntent":
            return []
        kws = []
        for slot in (intent.get("slots") or {}).values():
            if slot and slot.get("value"):
                val = slot["value"].get("interpretedValue") or slot["value"].get("originalValue")
                if val:
                    kws.extend(words(val))
        return kws
    except Exception as e:
        print("Lex error:", repr(e))
        return []


def search(keywords):
    terms = sorted({v for k in keywords for v in variants(k)})
    print("Search terms:", terms)
    body = {"size": 100,
            "query": {"bool": {"should": [{"match": {"labels": t}} for t in terms],
                               "minimum_should_match": 1}}}
    try:
        res = es_request("POST", f"/{INDEX}/_search", body)
    except urllib.error.HTTPError as e:
        print("ES error:", e.code, e.read()[:500])
        return []
    results = []
    for hit in res.get("hits", {}).get("hits", []):
        src = hit["_source"]
        url = s3.generate_presigned_url("get_object",
                                        Params={"Bucket": src["bucket"], "Key": src["objectKey"]},
                                        ExpiresIn=3600)
        results.append({"url": url, "labels": src.get("labels", []),
                        "objectKey": src["objectKey"]})
    return results


def lambda_handler(event, context):
    print("Event:", json.dumps(event))
    q = ((event.get("queryStringParameters") or {}).get("q")
         or event.get("q") or "").strip()

    keywords = lex_keywords(q) if q else []
    if not keywords and q:
        keywords = words(q)          # fallback if Lex missed the slot

    results = search(keywords) if keywords else []
    return {"statusCode": 200, "headers": CORS,
            "body": json.dumps({"results": results})}
