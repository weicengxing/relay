-- Generated from D:/freeclaude/chat_profiles.json
-- Execute after backend/src/main/resources/db/web_chat.sql if the tables do not exist yet.

update web_chat_model_configs
set
  name = 'account_1',
  base_url = 'https://chat.sharedchat.cc',
  model = 'gpt-5-5-thinking',
  auth_header = null,
  bearer_token = 'eyJhbGciOiJSUzI1NiIsImtpZCI6IjE5MzM0NGU2NS1iYmM5LTQ0ZDEtYTlkMC1mOTU3YjA3OWJkMGUiLCJ0eXAiOiJKV1QifQ.eyJhdWQiOlsiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS92MSJdLCJhenAiOiJwZGxMSVgyWTcyTUlsMnJoTGhURTlWVjliTjkwNWtCaCIsImNsaWVudF9pZCI6ImFwcF9XWHJGMUxTa2lUdGZZcWlMNlh0anlndlgiLCJleHAiOjE3NjIxOTY5MzQsImh0dHBzOi8vYXBpIjp7Im9wZW5haSI6eyJjb20vcHJvZmlsZSI6eyJlbWFpbCI6ImJ1aXNhbnZvd2EwMDEifX19LCJodHRwczovL2FwaS5vcGVuYWkuY29tL2F1dGgiOnsicG9pZCI6Im9yZy1WTFp6RTJva2E3TjVRRkk3Z21HdXlXY1kiLCJ1c2VyX2lkIjoidXNlci13bEo1S2FFR2tpUUdiV0xwU0VVMkUxYlcifSwiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS9wcm9maWxlIjp7ImVtYWlsIjoia2lyc3RpbmNoYWR3aWNrMjU3MTk4MGtkZUBnbWFpbC5jb20iLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZX0sImlhdCI6MTc2MTMzMjkzMywiaXNzIjoiaHR0cHM6Ly9hdXRoLm9wZW5haS5jb20iLCJqdGkiOiIxNmIxZjE4NS0xODljLTQ2ZmYtOGQzMi0wZmZhYWFlZTI0MTMiLCJuYmYiOjE3NjEzMzI5MzMsInB3ZF9hdXRoX3RpbWUiOjE3NTQwMzU3MDQsInNjcCI6WyJvcGVuaWQiLCJwcm9maWxlIiwiZW1haWwiLCJtb2RlbC5yZWFkIiwibW9kZWwucmVxdWVzdCIsIm9yZ2FuaXphdGlvbi5yZWFkIiwib3JnYW5pemF0aW9uLndyaXRlIiwib2ZmbGluZV9hY2Nlc3MiXSwic2Vzc2lvbl9pZCI6IjdybHZOejdlcHJiVXMxZFlHZ2drOW5sV29wSGVCOVAyIiwic3ViIjoiZ29vZ2xlLW9hdXRoMnwxMDUyMDMyOTQyNDE1NDE4MDY2MDUifQ.BBpzpYUorm_RsFv-JNNWELMXhhta36kNLh5S_59TJZQRyjYKxoIQfzjk3wJN_1Vd-ZNPgQ9eRTPMkdtrgah1dqgbLGkgg2T4oyJq4z-1tTLYb50t6g-vj2MW-YcArqouwmYL8avCGe90A_bL9LcxEwzL1hLtODSMn94mbLPCi26VPUBj9xwQJdP3deY-e2GpvIwbysz_eH-hP2vHooFhE0jebrE0FE-cuzyHU5b2h6YbzrfU_hwiPXuvGiZwON9LxndprXYuup5wzyNZEnufVTwDagGX5pCyGLSVk9bSILUz6zJkYMtFEBPyyDx-bL9hH041uDfDBUxi15w3hGVMgA',
  account_id = 'cd48e37a-45c6-4ee0-86b0-6d1d05bd3257',
  conduit_token = 'cger',
  sentinel_token = 'yyy',
  cookie = '_account_is_fedramp=false; _ga=GA1.1.798167618.1776071405; _account_residency_region=no_constraint; gfsessionid=s67yt20mmeh910didxh4z95udm18jplv; oai-gn=; oai-client-auth-info=%7B%22user%22%3A%7B%22name%22%3A%22nhnCJjNB%7C%22%2C%22email%22%3A%22nhnCJjNB%7C%22%2C%22picture%22%3A%22%2Favatars.png%22%2C%22connectionType%22%3A2%2C%22timestamp%22%3A1778307724018%7D%2C%22loggedInWithGoogleOneTap%22%3Afalse%2C%22isOptedOut%22%3Afalse%7D; oai-last-model-config=%7B%22model%22%3A%22gpt-5-5-thinking%22%2C%22effort%22%3A%22standard%22%7D; oai-default-model-config=%7B%22model%22%3A%22gpt-5-5%22%2C%22juices%22%3A%7B%7D%7D; _account=cd48e37a-45c6-4ee0-86b0-6d1d05bd3257; _ga_9SHBSK2D9J=GS2.1.s1778307724$o41$g1$t1778307735$j49$l0$h0; _dd_s=aid=9ae44759-8265-4fb2-9f5f-10e3cc0b9731&logs=1&id=166da275-75f7-4d03-8198-600acbb288d8&created=1778307722859&expire=1778309163862',
  oai_device_id = '7fe3b96c-7869-4eb0-b2fe-8426a534ea12',
  oai_session_id = '1f136a6e-011a-4f8f-a9b3-e6e9c511a1c1',
  oai_client_build_number = null,
  oai_client_version = null,
  oai_is = null,
  user_agent = null,
  call_prepare = false,
  enabled = true,
  updated_at = now()
where name = 'account_1';

insert into web_chat_model_configs (
  name,
  base_url,
  model,
  auth_header,
  bearer_token,
  account_id,
  conduit_token,
  sentinel_token,
  cookie,
  oai_device_id,
  oai_session_id,
  oai_client_build_number,
  oai_client_version,
  oai_is,
  user_agent,
  call_prepare,
  enabled
)
select
  'account_1',
  'https://chat.sharedchat.cc',
  'gpt-5-5-thinking',
  null,
  'eyJhbGciOiJSUzI1NiIsImtpZCI6IjE5MzM0NGU2NS1iYmM5LTQ0ZDEtYTlkMC1mOTU3YjA3OWJkMGUiLCJ0eXAiOiJKV1QifQ.eyJhdWQiOlsiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS92MSJdLCJhenAiOiJwZGxMSVgyWTcyTUlsMnJoTGhURTlWVjliTjkwNWtCaCIsImNsaWVudF9pZCI6ImFwcF9XWHJGMUxTa2lUdGZZcWlMNlh0anlndlgiLCJleHAiOjE3NjIxOTY5MzQsImh0dHBzOi8vYXBpIjp7Im9wZW5haSI6eyJjb20vcHJvZmlsZSI6eyJlbWFpbCI6ImJ1aXNhbnZvd2EwMDEifX19LCJodHRwczovL2FwaS5vcGVuYWkuY29tL2F1dGgiOnsicG9pZCI6Im9yZy1WTFp6RTJva2E3TjVRRkk3Z21HdXlXY1kiLCJ1c2VyX2lkIjoidXNlci13bEo1S2FFR2tpUUdiV0xwU0VVMkUxYlcifSwiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS9wcm9maWxlIjp7ImVtYWlsIjoia2lyc3RpbmNoYWR3aWNrMjU3MTk4MGtkZUBnbWFpbC5jb20iLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZX0sImlhdCI6MTc2MTMzMjkzMywiaXNzIjoiaHR0cHM6Ly9hdXRoLm9wZW5haS5jb20iLCJqdGkiOiIxNmIxZjE4NS0xODljLTQ2ZmYtOGQzMi0wZmZhYWFlZTI0MTMiLCJuYmYiOjE3NjEzMzI5MzMsInB3ZF9hdXRoX3RpbWUiOjE3NTQwMzU3MDQsInNjcCI6WyJvcGVuaWQiLCJwcm9maWxlIiwiZW1haWwiLCJtb2RlbC5yZWFkIiwibW9kZWwucmVxdWVzdCIsIm9yZ2FuaXphdGlvbi5yZWFkIiwib3JnYW5pemF0aW9uLndyaXRlIiwib2ZmbGluZV9hY2Nlc3MiXSwic2Vzc2lvbl9pZCI6IjdybHZOejdlcHJiVXMxZFlHZ2drOW5sV29wSGVCOVAyIiwic3ViIjoiZ29vZ2xlLW9hdXRoMnwxMDUyMDMyOTQyNDE1NDE4MDY2MDUifQ.BBpzpYUorm_RsFv-JNNWELMXhhta36kNLh5S_59TJZQRyjYKxoIQfzjk3wJN_1Vd-ZNPgQ9eRTPMkdtrgah1dqgbLGkgg2T4oyJq4z-1tTLYb50t6g-vj2MW-YcArqouwmYL8avCGe90A_bL9LcxEwzL1hLtODSMn94mbLPCi26VPUBj9xwQJdP3deY-e2GpvIwbysz_eH-hP2vHooFhE0jebrE0FE-cuzyHU5b2h6YbzrfU_hwiPXuvGiZwON9LxndprXYuup5wzyNZEnufVTwDagGX5pCyGLSVk9bSILUz6zJkYMtFEBPyyDx-bL9hH041uDfDBUxi15w3hGVMgA',
  'cd48e37a-45c6-4ee0-86b0-6d1d05bd3257',
  'cger',
  'yyy',
  '_account_is_fedramp=false; _ga=GA1.1.798167618.1776071405; _account_residency_region=no_constraint; gfsessionid=s67yt20mmeh910didxh4z95udm18jplv; oai-gn=; oai-client-auth-info=%7B%22user%22%3A%7B%22name%22%3A%22nhnCJjNB%7C%22%2C%22email%22%3A%22nhnCJjNB%7C%22%2C%22picture%22%3A%22%2Favatars.png%22%2C%22connectionType%22%3A2%2C%22timestamp%22%3A1778307724018%7D%2C%22loggedInWithGoogleOneTap%22%3Afalse%2C%22isOptedOut%22%3Afalse%7D; oai-last-model-config=%7B%22model%22%3A%22gpt-5-5-thinking%22%2C%22effort%22%3A%22standard%22%7D; oai-default-model-config=%7B%22model%22%3A%22gpt-5-5%22%2C%22juices%22%3A%7B%7D%7D; _account=cd48e37a-45c6-4ee0-86b0-6d1d05bd3257; _ga_9SHBSK2D9J=GS2.1.s1778307724$o41$g1$t1778307735$j49$l0$h0; _dd_s=aid=9ae44759-8265-4fb2-9f5f-10e3cc0b9731&logs=1&id=166da275-75f7-4d03-8198-600acbb288d8&created=1778307722859&expire=1778309163862',
  '7fe3b96c-7869-4eb0-b2fe-8426a534ea12',
  '1f136a6e-011a-4f8f-a9b3-e6e9c511a1c1',
  null,
  null,
  null,
  null,
  false,
  true
where not exists (
  select 1 from web_chat_model_configs where name = 'account_1'
);

update web_chat_model_configs
set
  name = 'account_2',
  base_url = 'https://chat.sharedchat.cc',
  model = 'gpt-5-5-thinking',
  auth_header = null,
  bearer_token = 'eyJhbGciOiJSUzI1NiIsImtpZCI6IjE5MzM0NGU2NS1iYmM5LTQ0ZDEtYTlkMC1mOTU3YjA3OWJkMGUiLCJ0eXAiOiJKV1QifQ.eyJhdWQiOlsiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS92MSJdLCJhenAiOiJwZGxMSVgyWTcyTUlsMnJoTGhURTlWVjliTjkwNWtCaCIsImNsaWVudF9pZCI6ImFwcF9XWHJGMUxTa2lUdGZZcWlMNlh0anlndlgiLCJleHAiOjE3NjIxOTY5MzQsImh0dHBzOi8vYXBpIjp7Im9wZW5haSI6eyJjb20vcHJvZmlsZSI6eyJlbWFpbCI6ImJ1aXNhbnZvd2EwMDEifX19LCJodHRwczovL2FwaS5vcGVuYWkuY29tL2F1dGgiOnsicG9pZCI6Im9yZy1WTFp6RTJva2E3TjVRRkk3Z21HdXlXY1kiLCJ1c2VyX2lkIjoidXNlci13bEo1S2FFR2tpUUdiV0xwU0VVMkUxYlcifSwiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS9wcm9maWxlIjp7ImVtYWlsIjoia2lyc3RpbmNoYWR3aWNrMjU3MTk4MGtkZUBnbWFpbC5jb20iLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZX0sImlhdCI6MTc2MTMzMjkzMywiaXNzIjoiaHR0cHM6Ly9hdXRoLm9wZW5haS5jb20iLCJqdGkiOiIxNmIxZjE4NS0xODljLTQ2ZmYtOGQzMi0wZmZhYWFlZTI0MTMiLCJuYmYiOjE3NjEzMzI5MzMsInB3ZF9hdXRoX3RpbWUiOjE3NTQwMzU3MDQsInNjcCI6WyJvcGVuaWQiLCJwcm9maWxlIiwiZW1haWwiLCJtb2RlbC5yZWFkIiwibW9kZWwucmVxdWVzdCIsIm9yZ2FuaXphdGlvbi5yZWFkIiwib3JnYW5pemF0aW9uLndyaXRlIiwib2ZmbGluZV9hY2Nlc3MiXSwic2Vzc2lvbl9pZCI6IjdybHZOejdlcHJiVXMxZFlHZ2drOW5sV29wSGVCOVAyIiwic3ViIjoiZ29vZ2xlLW9hdXRoMnwxMDUyMDMyOTQyNDE1NDE4MDY2MDUifQ.BBpzpYUorm_RsFv-JNNWELMXhhta36kNLh5S_59TJZQRyjYKxoIQfzjk3wJN_1Vd-ZNPgQ9eRTPMkdtrgah1dqgbLGkgg2T4oyJq4z-1tTLYb50t6g-vj2MW-YcArqouwmYL8avCGe90A_bL9LcxEwzL1hLtODSMn94mbLPCi26VPUBj9xwQJdP3deY-e2GpvIwbysz_eH-hP2vHooFhE0jebrE0FE-cuzyHU5b2h6YbzrfU_hwiPXuvGiZwON9LxndprXYuup5wzyNZEnufVTwDagGX5pCyGLSVk9bSILUz6zJkYMtFEBPyyDx-bL9hH041uDfDBUxi15w3hGVMgA',
  account_id = '842059c9-144b-4058-89ca-21f0f2b78f14',
  conduit_token = 'b8635660-b384-44ed-9381-e20cc8957d5f',
  sentinel_token = 'yyy',
  cookie = '_account_is_fedramp=false; gfsessionid=1vuoiuz1d5zsxndi6l5lq8sndw2pz332; oai-gn=; _account_residency_region=no_constraint; oai-default-model-config=%7B%22model%22%3A%22gpt-5-3%22%2C%22juices%22%3A%7B%7D%7D; oai-last-model-config=%7B%22model%22%3A%22gpt-5-5-thinking%22%2C%22effort%22%3A%22extended%22%7D; oai-client-auth-info=%7B%22user%22%3A%7B%22name%22%3A%22eRFulTrH%7C%22%2C%22email%22%3A%22eRFulTrH%7C%22%2C%22picture%22%3A%22%2Favatars.png%22%2C%22connectionType%22%3A2%2C%22timestamp%22%3A1777633486823%7D%2C%22loggedInWithGoogleOneTap%22%3Afalse%2C%22isOptedOut%22%3Afalse%7D; _account=842059c9-144b-4058-89ca-21f0f2b78f14; _dd_s=aid=9ae44759-8265-4fb2-9f5f-10e3cc0b9731&logs=1&id=a4b0c21d-4f9f-4dca-bc40-f75cb655ac11&created=1777630828451&expire=1777635852195; _ga=GA1.1.798167618.1776071405; _ga_9SHBSK2D9J=GS2.1.s1777633236$o24$g1$t1777633506$j40$l0$h0',
  oai_device_id = 'd66635a1-2331-499a-ad38-7f9803bfb09f',
  oai_session_id = '1f136a6e-011a-4f8f-a9b3-e6e9c511a1c1',
  oai_client_build_number = null,
  oai_client_version = null,
  oai_is = null,
  user_agent = null,
  call_prepare = false,
  enabled = true,
  updated_at = now()
where name = 'account_2';

insert into web_chat_model_configs (
  name,
  base_url,
  model,
  auth_header,
  bearer_token,
  account_id,
  conduit_token,
  sentinel_token,
  cookie,
  oai_device_id,
  oai_session_id,
  oai_client_build_number,
  oai_client_version,
  oai_is,
  user_agent,
  call_prepare,
  enabled
)
select
  'account_2',
  'https://chat.sharedchat.cc',
  'gpt-5-5-thinking',
  null,
  'eyJhbGciOiJSUzI1NiIsImtpZCI6IjE5MzM0NGU2NS1iYmM5LTQ0ZDEtYTlkMC1mOTU3YjA3OWJkMGUiLCJ0eXAiOiJKV1QifQ.eyJhdWQiOlsiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS92MSJdLCJhenAiOiJwZGxMSVgyWTcyTUlsMnJoTGhURTlWVjliTjkwNWtCaCIsImNsaWVudF9pZCI6ImFwcF9XWHJGMUxTa2lUdGZZcWlMNlh0anlndlgiLCJleHAiOjE3NjIxOTY5MzQsImh0dHBzOi8vYXBpIjp7Im9wZW5haSI6eyJjb20vcHJvZmlsZSI6eyJlbWFpbCI6ImJ1aXNhbnZvd2EwMDEifX19LCJodHRwczovL2FwaS5vcGVuYWkuY29tL2F1dGgiOnsicG9pZCI6Im9yZy1WTFp6RTJva2E3TjVRRkk3Z21HdXlXY1kiLCJ1c2VyX2lkIjoidXNlci13bEo1S2FFR2tpUUdiV0xwU0VVMkUxYlcifSwiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS9wcm9maWxlIjp7ImVtYWlsIjoia2lyc3RpbmNoYWR3aWNrMjU3MTk4MGtkZUBnbWFpbC5jb20iLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZX0sImlhdCI6MTc2MTMzMjkzMywiaXNzIjoiaHR0cHM6Ly9hdXRoLm9wZW5haS5jb20iLCJqdGkiOiIxNmIxZjE4NS0xODljLTQ2ZmYtOGQzMi0wZmZhYWFlZTI0MTMiLCJuYmYiOjE3NjEzMzI5MzMsInB3ZF9hdXRoX3RpbWUiOjE3NTQwMzU3MDQsInNjcCI6WyJvcGVuaWQiLCJwcm9maWxlIiwiZW1haWwiLCJtb2RlbC5yZWFkIiwibW9kZWwucmVxdWVzdCIsIm9yZ2FuaXphdGlvbi5yZWFkIiwib3JnYW5pemF0aW9uLndyaXRlIiwib2ZmbGluZV9hY2Nlc3MiXSwic2Vzc2lvbl9pZCI6IjdybHZOejdlcHJiVXMxZFlHZ2drOW5sV29wSGVCOVAyIiwic3ViIjoiZ29vZ2xlLW9hdXRoMnwxMDUyMDMyOTQyNDE1NDE4MDY2MDUifQ.BBpzpYUorm_RsFv-JNNWELMXhhta36kNLh5S_59TJZQRyjYKxoIQfzjk3wJN_1Vd-ZNPgQ9eRTPMkdtrgah1dqgbLGkgg2T4oyJq4z-1tTLYb50t6g-vj2MW-YcArqouwmYL8avCGe90A_bL9LcxEwzL1hLtODSMn94mbLPCi26VPUBj9xwQJdP3deY-e2GpvIwbysz_eH-hP2vHooFhE0jebrE0FE-cuzyHU5b2h6YbzrfU_hwiPXuvGiZwON9LxndprXYuup5wzyNZEnufVTwDagGX5pCyGLSVk9bSILUz6zJkYMtFEBPyyDx-bL9hH041uDfDBUxi15w3hGVMgA',
  '842059c9-144b-4058-89ca-21f0f2b78f14',
  'b8635660-b384-44ed-9381-e20cc8957d5f',
  'yyy',
  '_account_is_fedramp=false; gfsessionid=1vuoiuz1d5zsxndi6l5lq8sndw2pz332; oai-gn=; _account_residency_region=no_constraint; oai-default-model-config=%7B%22model%22%3A%22gpt-5-3%22%2C%22juices%22%3A%7B%7D%7D; oai-last-model-config=%7B%22model%22%3A%22gpt-5-5-thinking%22%2C%22effort%22%3A%22extended%22%7D; oai-client-auth-info=%7B%22user%22%3A%7B%22name%22%3A%22eRFulTrH%7C%22%2C%22email%22%3A%22eRFulTrH%7C%22%2C%22picture%22%3A%22%2Favatars.png%22%2C%22connectionType%22%3A2%2C%22timestamp%22%3A1777633486823%7D%2C%22loggedInWithGoogleOneTap%22%3Afalse%2C%22isOptedOut%22%3Afalse%7D; _account=842059c9-144b-4058-89ca-21f0f2b78f14; _dd_s=aid=9ae44759-8265-4fb2-9f5f-10e3cc0b9731&logs=1&id=a4b0c21d-4f9f-4dca-bc40-f75cb655ac11&created=1777630828451&expire=1777635852195; _ga=GA1.1.798167618.1776071405; _ga_9SHBSK2D9J=GS2.1.s1777633236$o24$g1$t1777633506$j40$l0$h0',
  'd66635a1-2331-499a-ad38-7f9803bfb09f',
  '1f136a6e-011a-4f8f-a9b3-e6e9c511a1c1',
  null,
  null,
  null,
  null,
  false,
  true
where not exists (
  select 1 from web_chat_model_configs where name = 'account_2'
);
