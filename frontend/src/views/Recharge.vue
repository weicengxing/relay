<script setup>
import { computed, onMounted, ref } from 'vue';
import * as api from '../api';
import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();
const amount = ref('');
const redeemCode = ref('');
const loading = ref(false);
const redeeming = ref(false);
const success = ref(false);
const error = ref('');
const redeemSuccess = ref('');
const showPaymentModal = ref(false);
const paymentRemarkCopied = ref(false);
const paymentImages = ref({ alipayQrImage: '', wechatQrImage: '' });
const presets = [10, 50, 100];
const paymentRemark = computed(() => auth.email || '');

onMounted(async () => {
  try {
    const bootstrap = await api.getBootstrap();
    paymentImages.value = bootstrap?.rechargePayment || paymentImages.value;
  } catch (e) {
    paymentImages.value = { alipayQrImage: '', wechatQrImage: '' };
  }
});

async function handleSubmit() {
  error.value = '';
  const val = parseFloat(amount.value);
  if (!val || val <= 0) { error.value = '请输入有效的充值金额'; return; }
  if (!paymentRemark.value) {
    error.value = '无法获取当前账号邮箱，请重新登录后再充值';
    return;
  }
  loading.value = true;
  try {
    await api.createRecharge(val, paymentRemark.value);
    showPaymentModal.value = true;
  } catch (e) {
    error.value = e.message || '充值失败';
  } finally { loading.value = false; }
}

function closePaymentModal() {
  showPaymentModal.value = false;
  paymentRemarkCopied.value = false;
  success.value = true;
  amount.value = '';
}

async function copyPaymentRemark() {
  const value = paymentRemark.value.trim();
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    paymentRemarkCopied.value = true;
    window.setTimeout(() => {
      paymentRemarkCopied.value = false;
    }, 1500);
  } catch (e) {
    paymentRemarkCopied.value = false;
  }
}

async function handleRedeem() {
  error.value = '';
  redeemSuccess.value = '';
  if (!redeemCode.value.trim()) {
    error.value = '请输入兑换码';
    return;
  }
  redeeming.value = true;
  try {
    const data = await api.redeemCode(redeemCode.value);
    auth.setBalance(data.balance);
    redeemSuccess.value = `兑换成功，已到账 ${Number(data.amount || 0).toFixed(2)}`;
    redeemCode.value = '';
  } catch (e) {
    error.value = e.message || '兑换失败';
  } finally {
    redeeming.value = false;
  }
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>充值</h1>
      <p>为你的账户充值以使用更多服务</p>
    </header>

    <div class="layout">
      <div class="card main-card">
        <div class="balance-strip">
          <div>
            <div class="bal-label">当前余额</div>
            <div class="bal-value">{{ auth.balance.toFixed(2) }}$</div>
          </div>
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><rect x="1" y="4" width="22" height="16" rx="3"/><line x1="1" y1="10" x2="23" y2="10"/></svg>
        </div>

        <form class="redeem-form" @submit.prevent="handleRedeem">
          <label class="field">
            <span class="field-label">兑换码</span>
            <div class="redeem-row">
              <input v-model="redeemCode" class="text-input" placeholder="输入兑换码" />
              <button type="submit" class="btn-submit redeem-btn" :disabled="redeeming">
                <span v-if="redeeming" class="spin"></span>
                {{ redeeming ? '兑换中...' : '兑换' }}
              </button>
            </div>
          </label>
          <div v-if="redeemSuccess" class="success-note">{{ redeemSuccess }}</div>
        </form>

        <transition name="fade" mode="out-in">
          <div v-if="success" class="success-box">
            <div class="success-icon">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            </div>
            <h3>充值申请已提交</h3>
            <p>等待管理员审核，审核通过后余额会自动更新</p>
            <button class="btn-submit" @click="success = false">继续充值</button>
          </div>

          <form v-else @submit.prevent="handleSubmit" class="form">
            <transition name="fade">
              <div v-if="error" class="alert">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                {{ error }}
              </div>
            </transition>

            <label class="field">
              <span class="field-label">充值金额</span>
              <div class="presets">
                <button v-for="p in presets" :key="p" type="button" class="preset" :class="{ active: amount === String(p) }" @click="amount = String(p)">{{ p }}</button>
              </div>
              <div class="amount-box">
                <span class="currency">¥</span>
                <input v-model="amount" type="number" min="1" step="0.01" placeholder="自定义金额" />
              </div>
            </label>

            <button type="submit" class="btn-submit" :disabled="loading">
              <span v-if="loading" class="spin"></span>
              {{ loading ? '提交中...' : '充值' }}
            </button>
          </form>
        </transition>
      </div>

      <div class="card side-card">
        <h3>充值说明</h3>
        <ul>
          <li>充值申请提交后需要管理员审核</li>
          <li>审核通过后余额会自动更新</li>
          <li>如有问题请联系管理员QQ 2629430873 微信号 DIQIUZUIQIANGNANREN</li>
          <li>管理员也只是一个清澈大学生，请多担待，但绝对秉持赤城之心为大家服务</li>
          <li>任何中转站一般很难维持稳定，建议不要大额充值~~</li>
          <li>支持自定义金额充值</li>
          <li>1元人民币可兑换10$</li>
          <li>如果服务您不满意，可以联系管理员申请退款 😊🌸</li>
        </ul>
      </div>
    </div>

    <div v-if="showPaymentModal" class="modal-backdrop" @click.self="closePaymentModal">
      <div class="payment-modal" role="dialog" aria-modal="true" aria-label="充值收款码">
        <div class="modal-head">
          <div>
            <h2>扫码完成充值</h2>
            <p>请支付 ¥{{ Number(amount || 0).toFixed(2) }}。付款备注必须填写下方邮箱。</p>
          </div>
          <button type="button" class="modal-close" aria-label="关闭" @click="closePaymentModal">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </div>

        <div class="payment-remark">
          <div>
            <span>微信/支付宝付款时，请在备注里填写</span>
            <strong>{{ paymentRemark }}</strong>
          </div>
          <button type="button" class="copy-btn" @click="copyPaymentRemark">
            {{ paymentRemarkCopied ? '已复制' : '复制' }}
          </button>
        </div>

        <div class="qr-grid">
          <div class="qr-card">
            <h3>支付宝</h3>
            <img v-if="paymentImages.alipayQrImage" :src="paymentImages.alipayQrImage" alt="支付宝收款码" />
            <div v-else class="qr-empty">请在 app_settings 配置 recharge.alipay_qr_image</div>
          </div>
          <div class="qr-card">
            <h3>微信</h3>
            <img v-if="paymentImages.wechatQrImage" :src="paymentImages.wechatQrImage" alt="微信收款码" />
            <div v-else class="qr-empty">请在 app_settings 配置 recharge.wechat_qr_image</div>
          </div>
        </div>

        <p class="modal-note">不要留空，也不要填写昵称。没有这个备注，管理员无法判断是哪一个账户付款。</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { animation: pageIn 0.4s var(--ease-out); }

@keyframes pageIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.page-head { margin-bottom: 24px; }
.page-head h1 { font-size: 26px; font-weight: 800; letter-spacing: -0.5px; }
.page-head p { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }

.layout {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 20px;
  align-items: start;
}

.card {
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.balance-strip {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 28px 28px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a78bfa 100%);
  color: #fff;
}

.redeem-form {
  padding: 22px 28px 0;
}

.redeem-row {
  display: grid;
  grid-template-columns: 1fr 112px;
  gap: 10px;
}

.redeem-btn {
  padding-inline: 18px;
}

.success-note {
  margin-top: 10px;
  color: var(--success);
  font-size: 13px;
  font-weight: 600;
}

.bal-label {
  font-size: 12px;
  font-weight: 600;
  opacity: 0.7;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.bal-value {
  font-size: 36px;
  font-weight: 800;
  letter-spacing: -1px;
  line-height: 1;
}

.success-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48px 28px;
  text-align: center;
}

.success-icon { color: var(--success); margin-bottom: 16px; }
.success-box h3 { font-size: 18px; font-weight: 700; margin-bottom: 6px; }
.success-box p { color: var(--text-secondary); font-size: 13px; margin-bottom: 24px; }

.form {
  padding: 28px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.presets {
  display: flex;
  gap: 8px;
}

.preset {
  flex: 1;
  padding: 10px;
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
  color: var(--text);
}

.preset:hover {
  border-color: var(--primary-glow);
  background: var(--primary-soft);
}

.preset.active {
  background: var(--text);
  color: #fff;
  border-color: var(--text);
}

.amount-box {
  display: flex;
  align-items: center;
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  transition: all var(--duration) var(--ease);
  background: var(--surface);
}

.amount-box:focus-within {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-glow);
}

.currency {
  padding: 0 14px;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-muted);
}

.amount-box input {
  flex: 1;
  padding: 12px 14px 12px 0;
  border: none;
  background: transparent;
  font-size: 15px;
  outline: none;
}

.amount-box input::placeholder { color: var(--text-muted); }

.text-input {
  padding: 11px 14px;
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 13px;
  outline: none;
  transition: all var(--duration) var(--ease);
  background: var(--surface);
}

.text-input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-glow);
}

.btn-submit {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 13px;
  background: var(--text);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.btn-submit:hover:not(:disabled) { background: #0f0f23; transform: translateY(-1px); box-shadow: var(--shadow-md); }
.btn-submit:disabled { opacity: 0.6; cursor: not-allowed; }

.spin {
  width: 16px; height: 16px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.alert {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--danger-soft);
  color: var(--danger);
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
}

.side-card {
  padding: 24px;
}

.side-card h3 {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 16px;
}

.side-card ul {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.side-card li {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  padding-left: 16px;
  position: relative;
}

.side-card li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--primary);
  opacity: 0.4;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(15, 23, 42, 0.42);
}

.payment-modal {
  width: min(680px, 100%);
  padding: 24px;
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: 0 24px 80px rgba(15, 23, 42, 0.26);
}

.modal-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 20px;
}

.modal-head h2 {
  font-size: 20px;
  font-weight: 800;
}

.modal-head p,
.modal-note {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
  margin-top: 6px;
}

.modal-close {
  width: 34px;
  height: 34px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-muted);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.modal-close:hover {
  color: var(--text);
  border-color: var(--text-muted);
}

.payment-remark {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  padding: 14px 16px;
  border: 2px solid rgba(245, 158, 11, 0.55);
  border-radius: var(--radius-sm);
  background: #fff7ed;
  box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.12);
}

.payment-remark span {
  display: block;
  margin-bottom: 6px;
  color: #9a3412;
  font-size: 12px;
  font-weight: 900;
}

.payment-remark strong {
  display: block;
  color: #7c2d12;
  font-size: 18px;
  font-weight: 900;
  overflow-wrap: anywhere;
}

.copy-btn {
  height: 34px;
  padding: 0 14px;
  border: 1px solid rgba(234, 88, 12, 0.35);
  border-radius: var(--radius-sm);
  background: #ea580c;
  color: #fff;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
  flex-shrink: 0;
}

.copy-btn:hover {
  background: #c2410c;
}

.qr-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.qr-card {
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
  text-align: center;
}

.qr-card h3 {
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 12px;
}

.qr-card img {
  width: 100%;
  max-width: 240px;
  aspect-ratio: 1;
  object-fit: contain;
  border-radius: var(--radius-sm);
  background: #fff;
}

.qr-empty {
  min-height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 18px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 768px) {
  .layout { grid-template-columns: 1fr; }
  .qr-grid { grid-template-columns: 1fr; }
}
</style>
