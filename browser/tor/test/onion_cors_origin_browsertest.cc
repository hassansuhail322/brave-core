// Copyright (c) 2026 The Brave Authors. All rights reserved.
// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this file,
// You can obtain one at https://mozilla.org/MPL/2.0/.

#include <map>
#include <memory>
#include <string>
#include <string_view>
#include <utility>

#include "base/functional/bind.h"
#include "base/synchronization/lock.h"
#include "base/thread_annotations.h"
#include "base/values.h"
#include "brave/browser/tor/tor_profile_manager.h"
#include "brave/components/tor/tor_navigation_throttle.h"
#include "brave/net/proxy_resolution/proxy_config_service_tor.h"
#include "chrome/test/base/in_process_browser_test.h"
#include "chrome/test/base/ui_test_utils.h"
#include "content/public/test/browser_test.h"
#include "content/public/test/browser_test_utils.h"
#include "content/public/test/content_mock_cert_verifier.h"
#include "net/dns/mock_host_resolver.h"
#include "net/test/embedded_test_server/embedded_test_server.h"
#include "net/test/embedded_test_server/http_request.h"
#include "net/test/embedded_test_server/http_response.h"
#include "url/gurl.h"

namespace {

constexpr char kPagePath[] = "/page.html";
constexpr char kDenyCorsPath[] = "/deny-cors";
constexpr char kAllowNullOriginPath[] = "/allow-null-origin";

constexpr char kFetchScript[] =
    "fetch($1, $2).then(() => 'allowed', () => 'blocked')";

}  // namespace

class OnionCorsOriginBrowserTest : public InProcessBrowserTest {
 public:
  OnionCorsOriginBrowserTest()
      : https_server_(net::EmbeddedTestServer::TYPE_HTTPS) {}

  void SetUpOnMainThread() override {
    InProcessBrowserTest::SetUpOnMainThread();
    mock_cert_verifier_.mock_cert_verifier()->set_default_result(net::OK);
    host_resolver()->AddRule("*", "127.0.0.1");
    https_server_.RegisterRequestMonitor(base::BindRepeating(
        &OnionCorsOriginBrowserTest::RecordOrigin, base::Unretained(this)));
    https_server_.RegisterRequestHandler(base::BindRepeating(
        &OnionCorsOriginBrowserTest::HandleRequest, base::Unretained(this)));
    ASSERT_TRUE(https_server_.Start());

    net::ProxyConfigServiceTor::SetBypassTorProxyConfigForTesting(true);
    tor::TorNavigationThrottle::SetSkipWaitForTorConnectedForTesting(true);
  }

  void SetUpCommandLine(base::CommandLine* command_line) override {
    InProcessBrowserTest::SetUpCommandLine(command_line);
    mock_cert_verifier_.SetUpCommandLine(command_line);
  }

  void SetUpInProcessBrowserTestFixture() override {
    InProcessBrowserTest::SetUpInProcessBrowserTestFixture();
    mock_cert_verifier_.SetUpInProcessBrowserTestFixture();
  }

  void TearDownInProcessBrowserTestFixture() override {
    mock_cert_verifier_.TearDownInProcessBrowserTestFixture();
    InProcessBrowserTest::TearDownInProcessBrowserTestFixture();
  }

  // Loads a page from a .onion origin in a Tor window.
  content::WebContents* OpenOnionPage() {
    BrowserWindowInterface* tor_browser =
        TorProfileManager::SwitchToTorProfile(browser()->GetProfile());
    const GURL page_url = https_server_.GetURL("foobar.onion", kPagePath);
    EXPECT_TRUE(ui_test_utils::NavigateToURL(tor_browser, page_url));
    return tor_browser->tab_strip_model()->GetActiveWebContents();
  }

  GURL CrossOriginURL(std::string_view path) {
    return https_server_.GetURL("a.com", path);
  }

  // The Origin header of the last `method` request for `path`, or "" if it had
  // none.
  std::string LastOrigin(std::string_view method, std::string_view path) {
    base::AutoLock auto_lock(lock_);
    return last_origin_[{std::string(method), std::string(path)}];
  }

 private:
  void RecordOrigin(const net::test_server::HttpRequest& request) {
    auto it = request.headers.find("Origin");
    base::AutoLock auto_lock(lock_);
    last_origin_[{request.method_string,
                  std::string(request.GetURL().path())}] =
        it == request.headers.end() ? "" : it->second;
  }

  std::unique_ptr<net::test_server::HttpResponse> HandleRequest(
      const net::test_server::HttpRequest& request) {
    auto response = std::make_unique<net::test_server::BasicHttpResponse>();
    const std::string path(request.GetURL().path());
    if (path == kPagePath) {
      response->set_content_type("text/html");
      response->set_content("<html></html>");
    } else if (path == kAllowNullOriginPath) {
      response->AddCustomHeader("Access-Control-Allow-Origin", "null");
    } else if (path != kDenyCorsPath) {
      return nullptr;
    }
    return response;
  }

  content::ContentMockCertVerifier mock_cert_verifier_;
  net::EmbeddedTestServer https_server_;
  base::Lock lock_;
  std::map<std::pair<std::string, std::string>, std::string> last_origin_
      GUARDED_BY(lock_);
};

IN_PROC_BROWSER_TEST_F(OnionCorsOriginBrowserTest, PreflightOrigin) {
  content::WebContents* web_contents = OpenOnionPage();

  // The server refuses CORS, so only the preflight reaches it.
  EXPECT_EQ("blocked",
            content::EvalJs(
                web_contents,
                content::JsReplace(kFetchScript, CrossOriginURL(kDenyCorsPath),
                                   base::DictValue().Set("method", "PUT"))));
  EXPECT_EQ(LastOrigin("OPTIONS", kDenyCorsPath), "null");
  EXPECT_EQ(LastOrigin("PUT", kDenyCorsPath), "");
}

IN_PROC_BROWSER_TEST_F(OnionCorsOriginBrowserTest, AllowNullOrigin) {
  content::WebContents* web_contents = OpenOnionPage();

  // The CORS check runs against the same opaque origin the request sent.
  EXPECT_EQ(
      "allowed",
      content::EvalJs(
          web_contents,
          content::JsReplace(kFetchScript, CrossOriginURL(kAllowNullOriginPath),
                             base::DictValue().Set("method", "GET"))));
  EXPECT_EQ(LastOrigin("GET", kAllowNullOriginPath), "null");
}
