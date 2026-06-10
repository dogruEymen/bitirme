# 12_FRONTEND_UX_IMPROVEMENTS.md — Research Workspace UX İyileştirme Planı

## Summary

Bu faz frontend'i tek bir koyu, yoğun ve araştırmacı odaklı çalışma alanına taşır. Chat, Bulletin ve Analytics aynı ürün hissiyle çalışmalı; hata, boş durum, loading ve destructive aksiyon davranışları sayfalar arasında tutarlı olmalıdır.

Audit bulguları:

- Uygulama kabuğu koyu, Dashboard/Bulletin açık tema; ürün hissi parçalı.
- Error/loading/empty state davranışları sayfa bazında dağınık ve bazen yanıltıcı.
- Bulletin seçim paneli güçlü ama ilk kullanım, kayıtlı tercih güncelleme ve uzun topic listeleri için fazla ham.
- Dashboard çok veri gösteriyor ama karar akışı zayıf; “neye bakmalıyım?” sorusuna yeterince rehberlik etmiyor.
- Chat deneyimi iyi başlangıçta, fakat kaynak/citation, timeout, resend ve session yönetimi daha güvenilir hale getirilmeli.
- Mobilde sidebar ve yoğun paneller var, fakat dashboard/bulletin taranabilirliği öncelikli optimize edilmemiş.

## Key Changes

### P0 — UX Tutarlılığı ve Temel Güven

- Layout, Chat, Dashboard, Bulletin ve Auth aynı koyu research workspace temasını kullanır.
- Ortak UI primitives kullanılır: `PageHeader`, `StateMessage`, `LoadingState`, `EmptyState`, `ConfirmDialog`.
- Frontend fetch hataları `ApiError` ile ayrıştırılır; network failure, auth expiry ve backend detail mesajları ayrılır.
- Chat session delete için confirm dialog zorunludur.
- Geçersiz localStorage kullanıcı kaydı 401 sonrası temizlenir ve auth ekranına yönlendirilir.

### P1 — Bulletin Deneyimi

- İlk kullanım ekranı tek odaklı onboarding olarak çalışır: cluster/category seçimi, arama, seçili sayısı ve create aksiyonu.
- Kayıtlı bültende topic yönetimi varsayılan olarak collapsed gelir; kullanıcı “Manage topics” ile açar.
- Topic listelerinde selected-only filtresi, clear ve update aksiyonları bulunur.
- Paper kartları akademik tarama için metadata, DOI/PDF/source aksiyonları, abstract expand ve digest highlight ayrımı sunar.
- Haftalık öne çıkanlar varsa ayrı section olarak gösterilir; yoksa sessizce gizlenir.

### P1 — Dashboard Deneyimi

- Dashboard “observe → diagnose → explore” akışıyla gruplanır.
- Filter bar compact/sticky davranır; filter değişiminde mevcut veri korunurken loading sinyali verilir.
- Grafikler koyu tema, okunabilir tooltip ve kısa açıklamalarla gösterilir.
- Cluster tablosunda arama, sıralama ve mobil overflow davranışı iyileştirilir.

### P2 — Chat ve Cross-Page Araştırma Akışı

- Chat yanıtlarında `Sources:` bölümü ayrı render edilir; plain text fallback korunur.
- Bulletin paper kartından chat’e “Ask” aksiyonu sunulur.
- Analytics cluster satırından ilgili araştırma aksiyonlarına geçiş planlanır.
- Markdown rendering mevcut bağımlılık eklemeden daha güvenli parse edilir; daha ileri renderer ayrı faza bırakılır.

## Public Interfaces / Types

- Backend API sözleşmesi korunur.
- Frontend ortak tipleri:
  - `ApiError`
  - `LoadableState<T>`
  - `PageStateKind = "loading" | "ready" | "empty" | "error"`
  - `ClusterOption`, `CategoryOption`, `BulletinPreferenceViewModel`
- Mevcut route'lar korunur: `/bulletin`, `/dashboard`, `/session/:sessionId`, `/auth`.

## Test Plan

- `npm run build`
- `npm run lint`
- Smoke test:
  - login/signup,
  - invalid stored user sonrası auth redirect,
  - Bulletin ilk kullanım topic seçimi,
  - kayıtlı bülten güncelleme,
  - Dashboard filtre değiştirme,
  - Chat yeni session, stream, resend, delete confirmation.
- Responsive kontrol:
  - 375px mobile,
  - 768px tablet,
  - 1280px desktop.
- Accessibility kontrol:
  - icon button `aria-label`,
  - form input label ilişkileri,
  - keyboard ile sidebar, filters, accordion, dialog,
  - görünür focus ring.

## Assumptions

- Ürün yönü: koyu temalı, yoğun ama okunabilir “Research workspace”.
- Öncelik: önce güvenilir ve tutarlı temel UX, sonra gelişmiş cross-page araştırma akışları.
- Yeni global state library eklenmez.
- UX için gereken veri frontend view model katmanında normalize edilir.
