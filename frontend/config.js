const isLocal =
  window.location.hostname === "127.0.0.1" ||
  window.location.hostname === "localhost";
window.API_BASE_URL = isLocal
  ? ""
  : "https://zpyabcm7pd.execute-api.ap-southeast-2.amazonaws.com/hackathon";

window.COGNITO_USER_POOL_ID = "ap-southeast-2_9qxZsapRA";
window.COGNITO_CLIENT_ID = "5skg43igmp066dn75n5qjknroa";
