import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import * as api from '../api';

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '');
  const userId = ref(localStorage.getItem('userId') || '');
  const email = ref(localStorage.getItem('email') || '');
  const balance = ref(parseFloat(localStorage.getItem('balance') || '0'));
  const billingGroup = ref(localStorage.getItem('billingGroup') || 'default');
  const costMultiplier = ref(parseFloat(localStorage.getItem('costMultiplier') || '1'));

  const isLoggedIn = computed(() => !!token.value);

  function saveSession(data) {
    token.value = data.token;
    userId.value = data.userId;
    email.value = data.email;
    balance.value = parseFloat(data.balance);
    billingGroup.value = data.billingGroup || 'default';
    costMultiplier.value = parseFloat(data.costMultiplier || '1');
    localStorage.setItem('token', data.token);
    localStorage.setItem('userId', data.userId);
    localStorage.setItem('email', data.email);
    localStorage.setItem('balance', String(data.balance));
    localStorage.setItem('billingGroup', billingGroup.value);
    localStorage.setItem('costMultiplier', String(costMultiplier.value));
  }

  function loginWithSession(data) {
    saveSession(data);
    return data;
  }

  async function register(emailAddr, password, verificationCode, turnstileToken = '') {
    const data = await api.register(emailAddr, password, verificationCode, turnstileToken);
    saveSession(data);
    return data;
  }

  async function login(emailAddr, password) {
    const data = await api.login(emailAddr, password);
    saveSession(data);
    return data;
  }

  function logout() {
    token.value = '';
    userId.value = '';
    email.value = '';
    balance.value = 0;
    billingGroup.value = 'default';
    costMultiplier.value = 1;
    localStorage.removeItem('token');
    localStorage.removeItem('userId');
    localStorage.removeItem('email');
    localStorage.removeItem('balance');
    localStorage.removeItem('billingGroup');
    localStorage.removeItem('costMultiplier');
  }

  function setBalance(nextBalance) {
    balance.value = parseFloat(nextBalance || 0);
    localStorage.setItem('balance', String(balance.value));
  }

  async function refreshBalance() {
    if (!token.value) return null;
    const data = await api.getBalance();
    setBalance(data?.balance);
    return data;
  }

  return {
    token,
    userId,
    email,
    balance,
    billingGroup,
    costMultiplier,
    isLoggedIn,
    register,
    login,
    loginWithSession,
    logout,
    setBalance,
    refreshBalance,
  };
});
