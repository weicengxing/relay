package com.relay.backend.module.auth;

import com.relay.backend.config.AppProperties;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public class SmtpVerificationMailSender implements VerificationMailSender {

  private static final Logger log = LoggerFactory.getLogger(SmtpVerificationMailSender.class);

  private final JavaMailSender javaMailSender;
  private final AppProperties appProperties;

  public SmtpVerificationMailSender(JavaMailSender javaMailSender, AppProperties appProperties) {
    this.javaMailSender = javaMailSender;
    this.appProperties = appProperties;
  }

  @Override
  public void sendRegisterCode(String email, String code, int ttlMinutes) {
    if (isBlank(appProperties.getMail().getUsername())
        || isBlank(appProperties.getMail().getPassword())
        || isBlank(appProperties.getMail().getFrom())) {
      log.warn("QQ SMTP is not configured yet; skipping verification email for {}", email);
      return;
    }

    try {
      MimeMessage mimeMessage = javaMailSender.createMimeMessage();
      MimeMessageHelper helper = new MimeMessageHelper(mimeMessage, "UTF-8");
      helper.setFrom(appProperties.getMail().getFrom());
      helper.setTo(email);
      helper.setSubject("Relay - 验证码");
      helper.setText(buildHtml(code, ttlMinutes), true);
      javaMailSender.send(mimeMessage);
    } catch (MessagingException exception) {
      log.error(
          "Failed to send verification email for {}; keeping generated code usable. code={}",
          email,
          code,
          exception);
    }
  }

  private String buildHtml(String code, int ttlMinutes) {
    String codeDigits = "";
    for (int i = 0; i < code.length(); i++) {
      codeDigits += "<td style=\"padding:0 6px\">" +
          "<div style=\"width:48px;height:56px;line-height:56px;text-align:center;" +
          "font-size:28px;font-weight:700;color:#1a1a2e;background:#f4f5f7;" +
          "border-radius:10px;font-family:'SF Mono',Consolas,monospace\">" +
          code.charAt(i) + "</div></td>";
    }

    return "<!DOCTYPE html>" +
        "<html><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0\"></head>" +
        "<body style=\"margin:0;padding:0;background:#f4f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif\">" +
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#f4f5f7;padding:32px 16px\">" +
        "<tr><td align=\"center\">" +
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"max-width:480px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.04)\">" +

        "<tr><td style=\"padding:36px 36px 0\">" +
        "<table cellpadding=\"0\" cellspacing=\"0\"><tr>" +
        "<td style=\"width:40px;height:40px;border-radius:10px;background:linear-gradient(135deg,#6366f1,#8b5cf6);text-align:center;vertical-align:middle\">" +
        "<span style=\"color:#fff;font-size:20px;line-height:40px\">&#9889;</span></td>" +
        "<td style=\"padding-left:10px;font-size:20px;font-weight:800;color:#1a1a2e;letter-spacing:-0.5px\">Relay</td>" +
        "</tr></table>" +
        "</td></tr>" +

        "<tr><td style=\"padding:32px 36px 0\">" +
        "<h1 style=\"margin:0;font-size:22px;font-weight:700;color:#1a1a2e;letter-spacing:-0.3px\">验证你的邮箱</h1>" +
        "<p style=\"margin:8px 0 0;font-size:14px;color:#6e7191;line-height:1.6\">你正在注册 Relay 账户，请使用以下验证码完成验证：</p>" +
        "</td></tr>" +

        "<tr><td style=\"padding:28px 36px\">" +
        "<table cellpadding=\"0\" cellspacing=\"0\" style=\"margin:0 auto\">" +
        "<tr>" + codeDigits + "</tr>" +
        "</table>" +
        "</td></tr>" +

        "<tr><td style=\"padding:0 36px 28px\">" +
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#f9fafb;border-radius:10px;padding:14px 18px\">" +
        "<tr><td style=\"font-size:13px;color:#6e7191;line-height:1.5\">" +
        "验证码有效期为 <strong style=\"color:#1a1a2e\">" + ttlMinutes + " 分钟</strong>。如果这不是你本人的操作，请忽略此邮件。" +
        "</td></tr></table>" +
        "</td></tr>" +

        "<tr><td style=\"padding:0 36px 32px\">" +
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"border-top:1px solid #f0f0f3;padding-top:20px\">" +
        "<tr><td style=\"font-size:12px;color:#a0a3bd;text-align:center;line-height:1.5\">" +
        "此邮件由系统自动发送，请勿回复<br>Relay AI 代理平台" +
        "</td></tr></table>" +
        "</td></tr>" +

        "</table></td></tr></table>" +
        "</body></html>";
  }

  private boolean isBlank(String value) {
    return value == null || value.isBlank();
  }
}
