# AI Photo Search — Cloud Computing & Big Data, Assignment 3

A photo album web app searchable in natural language ("show me dogs and trees").
Photos are labelled automatically by Amazon Rekognition (plus optional custom labels),
indexed in Amazon OpenSearch, and searched through an Amazon Lex bot.

**Live site:** http://kavya-photos-frontend-b1.s3-website-us-east-1.amazonaws.com

## Repository layout

| Folder | Contents |
|---|---|
| `front-end/` | Static site hosted on S3 (B1): `index.html`, `app.js`, `style.css`, `config.js`, and the API Gateway–generated JavaScript SDK (`sdk/`, SDK1) |
| `lambda-functions/` | `index-photos/` (LF1) and `search-photos/` (LF2), Python |
| `other-scripts/` | `template.yaml` (CloudFormation T1), `buildspec-lambdas.yml` (CodePipeline P1), `buildspec-frontend.yml` (CodePipeline P2) |

## Architecture

```
Browser (S3 static site B1, SDK1)
   │  GET /search?q=...            PUT /photos/{object}  (x-amz-meta-customLabels)
   ▼                                  ▼
API Gateway (REST, API key) ──────► S3 proxy ──► Photos bucket B2
   │                                               │ PUT event
   ▼                                               ▼
search-photos (LF2) ──► Amazon Lex (SearchIntent)  index-photos (LF1)
   │                                               ├─► Rekognition detectLabels
   │                                               ├─► S3 headObject (customLabels)
   ▼                                               ▼
        OpenSearch domain "photos", index "photos"
```

### Upload / index (LF1 `index-photos`)
1. Frontend `PUT /photos/{object}` → API Gateway S3 proxy → bucket B2. Custom labels travel as
   the `x-amz-meta-customLabels` header (e.g. `Sam, Sally`) and are stored as S3 object metadata.
2. The S3 PUT event triggers LF1, which calls Rekognition `detectLabels`, reads the custom labels
   with `headObject`, and stores this document in the `photos` index:

```json
{ "objectKey": "my-photo.jpg", "bucket": "my-photo-bucket",
  "createdTimestamp": "2018-11-05T12:40:02", "labels": ["sam", "sally", "dog", "pet"] }
```

### Search (LF2 `search-photos`)
1. `GET /search?q=show me dogs and cats` → LF2.
2. LF2 sends `q` to the Lex bot; `SearchIntent` returns slots `keyword1`/`keyword2`
   (handles keyword-only and sentence queries with one or two keywords).
3. Keywords are normalised (lowercase, singular/plural variants) and matched against `labels`
   in OpenSearch; any match returns the photo. No keywords → `{"results": []}`.
4. Each result returns a pre-signed S3 URL plus its labels.

## API (API Gateway, stage `prod`, API key required)

| Method | Path | Integration |
|---|---|---|
| `GET` | `/search?q={query}` | Lambda proxy → `search-photos` |
| `PUT` | `/photos/{object}` | AWS service proxy → S3 `PUT` into B2 (binary media types `image/*`) |

## CI/CD (CodePipeline)
- **P1 `photo-album-backend-pipeline`**: GitHub (this repo) → CodeBuild using
  `other-scripts/buildspec-lambdas.yml` → `aws lambda update-function-code` for both Lambdas.
- **P2 `photo-album-frontend-pipeline`**: GitHub (this repo) → CodeBuild using
  `other-scripts/buildspec-frontend.yml` (packages `front-end/`) → S3 deploy (extract) to B1.

## CloudFormation (T1)
`other-scripts/template.yaml` provisions both Lambdas (code inline), the REST API
(`/search` GET, `/photos/{object}` PUT, CORS, API key + usage plan, `prod` stage),
the photos bucket (with the PUT trigger) and a public website bucket, plus IAM roles.
Outputs include the public `WebsiteURL`. Parameters: OpenSearch endpoint/credentials and the Lex bot ID.

## Configuration
Lambda environment variables (not committed): `ES_HOST`, `ES_USER`, `ES_PASS`,
`BOT_ID`, `BOT_ALIAS_ID`, `LOCALE_ID`. Frontend API URL and key live in `front-end/config.js`.
