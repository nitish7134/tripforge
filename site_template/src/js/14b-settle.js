/* ---------- settle-up: minimum-transaction debt simplification (pure, reusable) ----------
   settle(balances) -> [{from, to, amount}]
   balances: {name: net}, net > 0 = is owed, net < 0 = owes; nets must sum to ~0.

   Why not greedy: the heap-based "biggest creditor pays biggest debtor" scheme always yields n-1 transfers
   (n = people with non-zero balance), which is optimal only when no proper subset of the balances already
   sums to zero. Minimum transfers = n - (max number of disjoint zero-sum subsets), so we maximise that count
   with a bitmask DP (Dreyfus-style), then settle each zero-sum group greedily, which is exact inside a group
   because a group with no zero-sum proper subset needs exactly |group|-1 transfers.
   Complexity O(2^n · n); fine for n <= 14. Beyond that we fall back to greedy. Amounts are rounded to the
   `unit` (default 1) so floating-point noise cannot create phantom cents. */
function settle(balances, unit = 1) {
  const names = Object.keys(balances).filter(k => Math.abs(balances[k]) >= unit / 2);
  const v = names.map(k => Math.round(balances[k] / unit));
  const drift = v.reduce((a, b) => a + b, 0);
  if (drift) v[v.indexOf(Math.max(...v))] -= drift; // push rounding residue onto the largest creditor
  const n = v.length;
  if (n === 0) return [];
  if (n > 14) return greedy(names, v).map(t => ({ ...t, amount: t.amount * unit }));
  const N = 1 << n, sum = new Int32Array(N), best = new Int8Array(N);
  for (let m = 1; m < N; m++) {
    const low = m & -m, i = 31 - Math.clz32(low);
    sum[m] = sum[m ^ low] + v[i];
    // best[m] = max zero-sum groups partitioning m: drop one member at a time, add 1 if m itself nets to zero
    let b = 0;
    for (let s = m; s; s &= s - 1) { const c = best[m ^ (s & -s)]; if (c > b) b = c; }
    best[m] = b + (sum[m] === 0 ? 1 : 0);
  }
  // recover a partition: peel off zero-sum groups that keep best[] optimal
  const groups = [];
  let rest = N - 1;
  while (rest) {
    let pick = rest; // find the smallest zero-sum subset g of rest with best[rest ^ g] === best[rest] - 1
    for (let g = rest; g; g = (g - 1) & rest) {
      if (sum[g] === 0 && best[rest ^ g] === best[rest] - 1 && bits(g) < bits(pick)) pick = g;
    }
    groups.push(pick);
    rest ^= pick;
  }
  const out = [];
  for (const g of groups) {
    const idx = [];
    for (let i = 0; i < n; i++) if (g >> i & 1) idx.push(i);
    out.push(...greedy(idx.map(i => names[i]), idx.map(i => v[i])));
  }
  return out.map(t => ({ ...t, amount: t.amount * unit }));
}
function bits(x) { let c = 0; while (x) { x &= x - 1; c++; } return c; }
function greedy(names, v) {
  const cr = [], db = [];
  v.forEach((a, i) => { if (a > 0) cr.push([names[i], a]); else if (a < 0) db.push([names[i], -a]); });
  cr.sort((a, b) => b[1] - a[1]); db.sort((a, b) => b[1] - a[1]);
  const out = [];
  let i = 0, j = 0;
  while (i < cr.length && j < db.length) {
    const x = Math.min(cr[i][1], db[j][1]);
    out.push({ from: db[j][0], to: cr[i][0], amount: x });
    cr[i][1] -= x; db[j][1] -= x;
    if (!cr[i][1]) i++;
    if (!db[j][1]) j++;
  }
  return out;
}
