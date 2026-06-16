# Pull Request

## Summary

<!-- What changed and why. Link issues: Fixes #N -->

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change (JSONL schema, CLI flags, or output columns)
- [ ] Documentation only
- [ ] Tests only

## Testing

```bash
make quality
make test
# uv run maps-timeline parse-file <dump>.xml   # if parser changed
```

- [ ] Offline tests pass (no phone required)
- [ ] Live device test performed (if scrape/navigation changed)

## Checklist

- [ ] Layer boundaries respected ([`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md))
- [ ] `maps_timeline/` at 100% test coverage
- [ ] Docs updated when behavior or CLI changed
- [ ] No `data/` or location PII committed
- [ ] Spanish UI selectors left untranslated
