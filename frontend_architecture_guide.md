# 前端基礎架構建議 (React + TypeScript)

此專案的前端可採用 **React + TypeScript + Vite** 來建置，並使用 **Axios** 來處理 HTTP 請求，以及 **Zustand** 作為全域狀態管理 (State Management) 工具。

## 1. API Client 攔截器 (Axios Interceptors)
為了滿足「Admin 身分模擬 (Impersonation)」功能需求，前端呼叫 API 時應該根據目前的全域狀態，自動在 Request Header 夾帶目標使用者 ID：

```typescript
// src/api/client.ts
import axios from 'axios';
import { useAuthStore } from '../stores/authStore';

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 10000,
});

apiClient.interceptors.request.use((config) => {
  const { user, impersonatedUserId } = useAuthStore.getState();
  
  if (user?.id) {
    config.headers['X-User-ID'] = user.id;
  }
  
  // 如果處於 Admin 模擬狀態，強制帶入 X-Impersonate-ID 供後端 Middleware 識別
  if (impersonatedUserId) {
    config.headers['X-Impersonate-ID'] = impersonatedUserId;
  }
  
  return config;
});

export default apiClient;
```

## 2. 全域狀態管理 (Zustand)
使用狀態管理工具來儲存目前的登入者與「被模擬的目標使用者」。這樣當 Admin 按下「切換身分」按鈕時，整個 App 的 API 呼叫都能自動反應。

```typescript
// src/stores/authStore.ts
import { create } from 'zustand';

interface User {
  id: string;
  username: string;
  role: 'user' | 'admin';
}

interface AuthState {
  user: User | null;
  impersonatedUserId: string | null;
  login: (user: User) => void;
  logout: () => void;
  startImpersonation: (targetId: string) => void;
  stopImpersonation: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null, // 例如目前登入的是 Admin
  impersonatedUserId: null, // Admin 正在看的另外一位客戶
  
  login: (user) => set({ user }),
  logout: () => set({ user: null, impersonatedUserId: null }),
  
  startImpersonation: (targetId) => set({ impersonatedUserId: targetId }),
  stopImpersonation: () => set({ impersonatedUserId: null }),
}));
```

## 3. UI 呈現防呆提示
當 `impersonatedUserId` 存在時，可以在畫面上方顯示警告 Header：「您正在以管理員身分檢視 [用戶 X] 的資料，所有的修改操作皆會被記錄。」

```tsx
// src/components/ImpersonateBanner.tsx
import { useAuthStore } from '../stores/authStore';

export const ImpersonateBanner = () => {
    const { impersonatedUserId, stopImpersonation } = useAuthStore();

    if (!impersonatedUserId) return null;

    return (
        <div className="bg-red-500 text-white p-2 text-center flex justify-between">
            <span>⚠️ 警告：目前處於客戶身分模擬模式。所有寫入動作均會寫入稽核。</span>
            <button onClick={stopImpersonation} className="underline">結束模擬</button>
        </div>
    );
}
```

## 總結
1. 將所有 API 請求封裝在 `apiClient` 內。
2. Admin 要幫助客戶排除障礙時，呼叫 `startImpersonation(客戶ID)`。
3. 後續元件 (如投資組合總覽、推薦清單) 都不需要修改任何邏輯，Axios 攔截器會自動向 FastAPI 以被模擬者的身分要資料。
4. 一旦修改資料 (POST/PUT/DELETE)，後端 FastAPI 內的 Middleware 會自動攔截並強制 INSERT 至 `Audit_Logs`。
