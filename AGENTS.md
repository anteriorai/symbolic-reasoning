# Agent instructions

Follow the [Tenets](CONTRIBUTING.md#tenets) and the rest of [CONTRIBUTING.md](CONTRIBUTING.md). The code standards below apply to Python and TypeScript alike.

## Code standards

1. **No casts or `Any`.** Do not use `typing.cast`, `Any`, TypeScript `as` casts, or `any`. Fix the types instead.
2. **No hacks.** Solve the actual problem rather than working around it.
3. **Less code is better than more.** Prefer the shortest implementation that reads clearly, and do not write code you do not need yet.
4. **Be elegant.** Among working solutions, choose the cleanest one.
5. **Use your libraries.** If a dependency already provides a feature, use it instead of reimplementing it.
6. **Have taste.** Write code you would be glad to review.
7. **No monkeypatching in tests.** Do not use pytest's `monkeypatch` fixture or `unittest.mock.patch` to replace attributes at runtime; pass test doubles in explicitly instead.
8. **No defensive programming.** Fail fast and loud: do not guard against states that cannot happen, add silent fallbacks, or catch an error only to carry on.
9. **Test behaviour, not implementation.** Assert what the code does through its public interface, not how it does it, so a refactor that keeps the behaviour keeps the tests green.
