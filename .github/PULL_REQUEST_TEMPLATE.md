## Что меняется

Краткое описание изменения — что и зачем.

## Проверки (обязательно зелёные перед merge)

- [ ] `ruff check app/ tests/`
- [ ] `mypy --strict app/`
- [ ] `pytest -v` (89 passed)
- [ ] `cd web && pnpm check` (0 errors)

> Backend и web проверяются отдельно — web-only правка всё равно требует `pnpm check`.

## Тип изменения

- [ ] 🐛 Bug fix
- [ ] ✨ Feature
- [ ] 📝 Docs
- [ ] 🧪 Tests
- [ ] 🔧 Refactor

## Правила проекта (SSOT)

- [ ] Никаких хардкод-провайдеров/моделей — только через БД
- [ ] Абсолютные импорты (`from app...`)
- [ ] Ошибки — значения (`AppError`), не `except: pass`
- [ ] `api_key`/`Authorization`/`key_hash` не логируются целиком (первые 8 символов)
- [ ] SQLite-миграции через `batch_alter_table` (если трогал схему)

## Связанные issues

Closes #...
