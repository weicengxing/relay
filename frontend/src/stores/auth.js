import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import * as api from '../api';

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '');
  const userId = ref(localStorage.getItem('userId') || '');
  const email = ref(localStorage.getItem('email') || '');
  const balance = ref(parseFloat(localStorage.getItem('balance') || '0'));

  const isLoggedIn = computed(() => !!token.value);

  function saveSession(data) {
    token.value = data.token;
    userId.value = data.userId;
    email.value = data.email;
    balance.value = parseFloat(data.balance);
    localStorage.setItem('token', data.token);
    localStorage.setItem('userId', data.userId);
    localStorage.setItem('email', data.email);
    localStorage.setItem('balance', String(data.balance));
  }

  async function register(emailAddr, password, verificationCode) {
    const data = await api.register(emailAddr, password, verificationCode);
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
    localStorage.removeItem('token');
    localStorage.removeItem('userId');
    localStorage.removeItem('email');
    localStorage.removeItem('balance');
  }

  function setBalance(nextBalance) {
    balance.value = parseFloat(nextBalance || 0);
    localStorage.setItem('balance', String(balance.value));
  }

  return { token, userId, email, balance, isLoggedIn, register, login, logout, setBalance };
});
