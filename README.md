# distributed-systems

### Пример. Поиск слова «hg9f»

**Отправка задачи (maxLength = 4):**

```cmd
curl -X POST http://localhost:8080/api/hash/crack \
  -H "Content-Type: application/json" \
  -d '{"hash":"e307e08cc61dba413a2362bb93613ff8", "maxLength":4}'
```

**Пример ожидаемого ответа от менеджера:**

```json
{"RequestId": "d945e077-0792-46f3-8b09-c209a8f2fa85"}
```

**Проверка статуса:**

```cmd
curl "http://localhost:8080/api/hash/status?requestId=<ВАШ_REQUEST_ID>"
```

**Ожидаемый результат:**

```json
{"status": "READY", "progress": "100%", "data": ["hg9f"]}
```

### Особенности работы

- В случае если один из воркеров выйдет из строя и после заданного кол-ва ретраев он не поднимется, статус сменится на `ERROR`. Однако, частичный результат можно будет увидеть в поле `partial_result` несмотря на ошибку и он будет правильным.
- Если задача еще стоит в очереди на выполнение у нее будет статус `NEW`.

---
