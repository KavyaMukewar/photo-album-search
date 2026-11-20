import json, os, base64, urllib.request, urllib.parse
import boto3

s3 = boto3.client("s3")
rek = boto3.client("rekognition")

ES_HOST = os.environ["ES_HOST"].rstrip("/")
ES_USER = os.environ["ES_USER"]
ES_PASS = os.environ["ES_PASS"]
INDEX = "photos"


def es_request(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(ES_HOST + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    token = base64.b64encode(f"{ES_USER}:{ES_PASS}".encode()).decode()
    req.add_header("Authorization", "Basic " + token)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def lambda_handler(event, context):
    print("Event:", json.dumps(event))
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        # 1. Rekognition labels
        rek_resp = rek.detect_labels(
            Image={"S3Object": {"Bucket": bucket, "Name": key}},
            MaxLabels=20, MinConfidence=70)
        rek_labels = [l["Name"].strip().lower() for l in rek_resp["Labels"]]

        # 2. Custom labels from x-amz-meta-customLabels (S3 lowercases metadata keys)
        head = s3.head_object(Bucket=bucket, Key=key)
        custom_raw = head.get("Metadata", {}).get("customlabels", "")
        custom_labels = [c.strip().lower() for c in custom_raw.split(",") if c.strip()]

        # 3. A1 = custom labels + Rekognition labels (deduped, order kept)
        labels = list(dict.fromkeys(custom_labels + rek_labels))

        doc = {
            "objectKey": key,
            "bucket": bucket,
            "createdTimestamp": head["LastModified"].strftime("%Y-%m-%dT%H:%M:%S"),
            "labels": labels,
        }
        doc_id = urllib.parse.quote(key, safe="")
        resp = es_request("PUT", f"/{INDEX}/_doc/{doc_id}", doc)
        print("Indexed:", json.dumps(doc), "->", resp.get("result"))

    return {"statusCode": 200, "body": "ok"}
