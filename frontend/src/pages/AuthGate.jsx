import { useEffect, useState } from "react";
import {
  ArrowLeft, ArrowRight, BookOpen, Eye, EyeOff, LoaderCircle, LockKeyhole, Mail, Moon, Phone, Sparkles, Sun, UserRound,
} from "lucide-react";

import { API, apiFetch } from "../services/api";
import TimedFeedback from "../components/TimedFeedback";

const REMEMBERED_EMAIL_KEY = "researchmate.rememberedEmail";

function getRememberedEmail() {
  try {
    return window.localStorage.getItem(REMEMBERED_EMAIL_KEY) || "";
  } catch (error) {
    console.warn("Could not read the remembered sign-in email.", error);
    return "";
  }
}

async function readResponse(response, fallback) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || fallback);
  return data;
}

export default function AuthGate({
  initialMode = "login",
  colorMode = "light",
  onColorModeChange,
  onAuthenticated,
  onBackToHome,
}) {
  const [mode, setMode] = useState(initialMode);
  const [email, setEmail] = useState(getRememberedEmail);
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(() => Boolean(getRememberedEmail()));
  const [loginMethod, setLoginMethod] = useState("email");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [smsChallengeId, setSmsChallengeId] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const isDark = colorMode === "dark";
  const [emailConfigured, setEmailConfigured] = useState(null);
  const [smsEnabled, setSmsEnabled] = useState(false);
  const [oauthProviders, setOauthProviders] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [resetToken, setResetToken] = useState(
    () => new URLSearchParams(window.location.search).get("reset_password") || "",
  );

  useEffect(() => {
    let active = true;
    apiFetch(API.authConfig)
      .then((response) => readResponse(response, "Could not load sign-in options."))
      .then((config) => {
        if (active) {
          setOauthProviders([
            {
              id: "google",
              label: "Google",
              start: API.googleStart,
              enabled: config.google_enabled === true,
            },
            {
              id: "github",
              label: "GitHub",
              start: API.githubStart,
              enabled: config.github_enabled === true,
            },
            {
              id: "linkedin",
              label: "LinkedIn",
              start: API.linkedinStart,
              enabled: config.linkedin_enabled === true,
            },
          ]);
          setEmailConfigured(config.email_configured === true);
          setSmsEnabled(config.sms_enabled === true);
        }
      })
      .catch(() => {
        if (active) {
          setOauthProviders([]);
          setEmailConfigured(null);
          setSmsEnabled(false);
        }
      });

    const params = new URLSearchParams(window.location.search);
    const verifyToken = params.get("verify_email");
    const resetLinkToken = params.get("reset_password");
    if (verifyToken) {
      setBusy(true);
      apiFetch(API.verifyEmail, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: verifyToken }),
      })
        .then((response) => readResponse(response, "Email verification failed."))
        .then((data) => {
          setMode("login");
          setResetToken("");
          setNotice(data.message);
        })
        .catch((err) => setError(err.message))
        .finally(() => setBusy(false));
    } else if (resetLinkToken) {
      setMode("reset");
      setNotice("Choose a new password for your account.");
    }

    if (verifyToken || resetLinkToken) {
      window.history.replaceState({}, "", window.location.pathname);
    }

    return () => {
      active = false;
    };
  }, []);

  async function submit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    setError("");
    setNotice("");

    if (mode === "register" && password !== confirmPassword) {
      setError("The passwords do not match.");
      return;
    }

    setBusy(true);
    try {
      if (mode === "login") {
        if (loginMethod === "phone") {
          if (!smsChallengeId) {
            const data = await readResponse(
              await apiFetch(API.sendPhoneLoginCode, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ phone_number: phoneNumber }),
              }),
              "Could not send a verification code.",
            );
            setSmsChallengeId(data.challenge_id);
            setVerificationCode("");
            setNotice(data.message);
            return;
          }
          const data = await readResponse(
            await apiFetch(`${API.verifyPhoneLoginCode}?remember_me=false`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ challenge_id: smsChallengeId, code: verificationCode }),
            }),
            "Could not verify the sign-in code.",
          );
          onAuthenticated(data.user);
          return;
        }
        const data = await readResponse(
          await apiFetch(API.login, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password, remember_me: rememberMe }),
          }),
          "Could not sign in.",
        );
        if (rememberMe) {
          try {
            window.localStorage.setItem(REMEMBERED_EMAIL_KEY, email);
          } catch (storageError) {
            console.warn("Could not save the remembered sign-in email.", storageError);
          }
          if (window.PasswordCredential && navigator.credentials?.store && form) {
            try {
              await navigator.credentials.store(new window.PasswordCredential(form));
            } catch (credentialError) {
              console.warn("The browser password manager could not save this login.", credentialError);
            }
          }
        } else {
          try {
            window.localStorage.removeItem(REMEMBERED_EMAIL_KEY);
          } catch (storageError) {
            console.warn("Could not clear the remembered sign-in email.", storageError);
          }
        }
        onAuthenticated(data.user);
      } else if (mode === "register") {
        const data = await readResponse(
          await apiFetch(API.register, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
          }),
          "Could not create your account.",
        );
        setMode("login");
        setPassword("");
        setConfirmPassword("");
        setNotice(data.message);
      } else if (mode === "forgot") {
        const data = await readResponse(
          await apiFetch(API.forgotPassword, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email }),
          }),
          "Could not request a password reset.",
        );
        setNotice(data.message);
      } else if (mode === "reset") {
        const data = await readResponse(
          await apiFetch(API.resetPassword, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token: resetToken, password }),
          }),
          "Could not reset your password.",
        );
        setMode("login");
        setPassword("");
        setNotice(data.message);
      }
    } catch (err) {
      setError(err.message || "The request failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function resendVerification() {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const data = await readResponse(
        await apiFetch(API.resendVerification, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email }),
        }),
        "Could not resend the verification email.",
      );
      setNotice(data.message);
    } catch (err) {
      setError(err.message || "Could not resend the verification email.");
    } finally {
      setBusy(false);
    }
  }

  const isRegister = mode === "register";
  const isLogin = mode === "login";
  const isPhoneLogin = isLogin && loginMethod === "phone";
  const isReset = mode === "reset";
  const title = isRegister ? "Create your account"
    : isReset ? "Set a new password"
      : mode === "forgot" ? "Reset your password"
        : isPhoneLogin ? "Log in to continue your learning journey"
          : "Welcome back";

  return (
    <main className={`auth-page${isDark ? " auth-page-dark" : ""}${isPhoneLogin ? " auth-page-sms" : ""}`}>
      {onBackToHome && !isReset && mode !== "forgot" && (
        <button className="auth-home-button" type="button" onClick={onBackToHome}>
          <ArrowLeft size={18} />
          <span>Back to home</span>
        </button>
      )}
      <button
        className="auth-theme-toggle"
        type="button"
        aria-label={`Switch to ${isDark ? "light" : "dark"} theme`}
        onClick={() => onColorModeChange?.(isDark ? "light" : "dark")}
      >
        {isDark ? <Sun size={19} /> : <Moon size={19} />}
      </button>
      <section className={`auth-card${isPhoneLogin ? " auth-card-sms" : ""}`}>
        <div className="auth-logo" aria-label="ResearchMate">
          <div className="auth-logo-tile">
            <BookOpen size={48} strokeWidth={1.7} />
            <Sparkles className="auth-logo-sparkle" size={18} />
          </div>
          <span className="auth-wordmark">Research<span>Mate</span></span>
        </div>
        <h1>{title}</h1>
        {isPhoneLogin && (
          <>
            <div className="auth-sms-avatar" aria-hidden="true"><UserRound size={32} /></div>
            <p className="auth-sms-welcome">Welcome back</p>
          </>
        )}
        <p className="auth-description">
          {isRegister
            ? "Create an account to keep your papers and summaries private."
            : isLogin
              ? isPhoneLogin
                ? smsChallengeId
                  ? `If this number is linked to an account, we’ll text ${phoneNumber} a code for a secure passwordless log-in.`
                  : phoneNumber
                    ? `If this number is linked to an account, we’ll text ${phoneNumber} a code for a secure passwordless log-in.`
                    : "Enter your phone number to receive a secure passwordless log-in code."
                : "Sign in to continue"
              : "We’ll send a secure link to the email address on your account."}
        </p>

        <form id="researchmate-login-form" className="auth-form" autoComplete="on" onSubmit={submit}>
          {!isReset && !(isPhoneLogin && smsChallengeId) && (
            <label>
              {isPhoneLogin ? "Phone number" : "Email address"}
              <span className="auth-input-wrap">
                {isPhoneLogin ? <Phone size={17} /> : <Mail size={17} />}
                <input
                  name={isPhoneLogin ? "phone_number" : "email"}
                  type={isPhoneLogin ? "tel" : "email"}
                  autoComplete={isPhoneLogin ? "tel" : isLogin ? "username" : "email"}
                  inputMode={isPhoneLogin ? "tel" : undefined}
                  placeholder={isPhoneLogin ? "+14155552671" : "Email address"}
                  aria-label={isPhoneLogin ? "Phone number" : "Email address"}
                  value={isPhoneLogin ? phoneNumber : email}
                  onChange={(event) => {
                    if (isPhoneLogin) setPhoneNumber(event.target.value);
                    else setEmail(event.target.value);
                  }}
                  required
                />
              </span>
            </label>
          )}
          {isPhoneLogin && smsChallengeId && (
            <label>
              Verification code
              <span className="auth-input-wrap">
                <LockKeyhole size={17} />
                <input
                  name="one-time-code"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="Enter the code from your text"
                  aria-label="Verification code"
                  value={verificationCode}
                  onChange={(event) => setVerificationCode(event.target.value.replace(/\D/g, "").slice(0, 10))}
                  required
                />
              </span>
            </label>
          )}
          {mode !== "forgot" && !isPhoneLogin && (
            <label>
              {isReset ? "New password" : "Password"}
              <span className="auth-input-wrap">
                <LockKeyhole size={17} />
                <input
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete={isRegister || isReset ? "new-password" : "current-password"}
                  placeholder={isReset ? "New password" : "Password"}
                  aria-label={isReset ? "New password" : "Password"}
                  minLength={10}
                  maxLength={256}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />
                <button
                  className="auth-password-toggle"
                  type="button"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((visible) => !visible)}
                >
                  {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </span>
              {(isRegister || isReset) && (
                <small>Use at least 10 characters.</small>
              )}
            </label>
          )}
          {isLogin && !isPhoneLogin && (
            <div className="auth-options">
              <label className="auth-remember-me">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(event) => setRememberMe(event.target.checked)}
                />
                Remember me
              </label>
              <button
                className="auth-forgot-link"
                type="button"
                onClick={() => { setMode("forgot"); setError(""); setNotice(""); }}
              >
                Forgot password?
              </button>
            </div>
          )}
          {isLogin && !isPhoneLogin && (
            <small className="auth-remember-hint">
              Saves your email on this device and keeps you signed in for 14 days. Your browser
              can offer to remember your password securely.
            </small>
          )}
          {isPhoneLogin && (
            <small className="auth-remember-hint">
              {smsChallengeId
                ? `Enter the one-time code sent to ${phoneNumber}.`
                : "We’ll text a secure one-time code to your phone. Enter the number in international format."}
            </small>
          )}
          {isRegister && (
            <label>
              Confirm password
              <span className="auth-input-wrap">
                <LockKeyhole size={17} />
                <input
                  type={showConfirmPassword ? "text" : "password"}
                  autoComplete="new-password"
                  minLength={10}
                  maxLength={256}
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  required
                />
                <button
                  className="auth-password-toggle"
                  type="button"
                  aria-label={showConfirmPassword ? "Hide confirm password" : "Show confirm password"}
                  aria-pressed={showConfirmPassword}
                  onClick={() => setShowConfirmPassword((visible) => !visible)}
                >
                  {showConfirmPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </span>
            </label>
          )}
          {isRegister && emailConfigured === false && (
            <p className="auth-message auth-warning" role="status">
              The backend is not detecting SMTP settings. Confirm SMTP_HOST and SMTP_FROM in
              backend/.env, then restart the backend.
            </p>
          )}
          {error && (
            <TimedFeedback as="p" className="auth-message error-message" role="alert" message={error}>
              {error}
            </TimedFeedback>
          )}
          {notice && (
            <TimedFeedback as="p" className="auth-message auth-notice" role="status" message={notice}>
              {notice}
            </TimedFeedback>
          )}
          <button className="primary-button auth-submit" type="submit" disabled={busy}>
            <span>{busy ? "Please wait..." : isRegister ? "Create account"
              : isReset ? "Save new password"
                : mode === "forgot" ? "Send reset link"
                  : isPhoneLogin ? smsChallengeId ? "Verify and continue" : "Send code"
                    : "Login"}</span>
            {busy
              ? <LoaderCircle className="spin" size={19} />
              : <span className="auth-submit-arrow"><ArrowRight size={21} /></span>}
          </button>
        </form>

        {isLogin && (
          <div className="auth-help-links">
            <button
              type="button"
              onClick={() => {
                if (isPhoneLogin && smsChallengeId) {
                  setPhoneNumber("");
                  setSmsChallengeId("");
                  setVerificationCode("");
                } else {
                  setLoginMethod(isPhoneLogin ? "email" : "phone");
                  setSmsChallengeId("");
                  setVerificationCode("");
                }
                setError("");
                setNotice("");
              }}
            >
              {isPhoneLogin
                ? smsChallengeId ? "Log in to a different account" : "Use email and password instead"
                : "Sign in with phone"}
            </button>
          </div>
        )}
        {isLogin && !smsEnabled && emailConfigured !== null && (
          <p className="auth-provider-note">
            Phone sign-in is unavailable until Twilio Verify is configured in backend/.env.
          </p>
        )}

        {isLogin && !isPhoneLogin && (
          <div className="auth-help-links">
            <button type="button" onClick={resendVerification} disabled={!email || busy}>
              Resend verification email
            </button>
          </div>
        )}

        {oauthProviders.length > 0 && ((isLogin && !isPhoneLogin) || isRegister) && (
          <>
            <div className="auth-divider"><span>Or continue with</span></div>
            <div className="auth-oauth-buttons">
              {oauthProviders.map(({ id, label, start, enabled }) => (
                <button
                  className={`secondary-button auth-google-button auth-social-${id}`}
                  type="button"
                  key={id}
                  disabled={!enabled}
                  title={enabled ? undefined : `${label} sign-in is not configured on the backend.`}
                  onClick={() => { window.location.href = start; }}
                >
                  <span className="auth-social-icon">
                    <img src={`/social-logos/${id}.svg?v=1`} alt="" />
                  </span>
                  <span className="auth-social-label">{label}</span>
                  {!enabled && <small className="auth-provider-status">Setup required</small>}
                </button>
              ))}
            </div>
            {oauthProviders.some((provider) => !provider.enabled) && (
              <p className="auth-provider-note">
                Buttons marked “Setup required” need provider credentials in backend/.env and a
                backend restart.
              </p>
            )}
          </>
        )}

        <p className="auth-switch">
          {isPhoneLogin ? "Don't have an account?" : isLogin ? "New to ResearchMate?" : "Already have an account?"}{" "}
          <button
            type="button"
            onClick={() => {
              setMode(isLogin ? "register" : "login");
              setLoginMethod("email");
              setSmsChallengeId("");
              setVerificationCode("");
              setError("");
              setNotice("");
            }}
          >
            {isPhoneLogin ? "Sign up" : isLogin ? "Create an account" : "Sign in"}
          </button>
        </p>
      </section>
    </main>
  );
}
