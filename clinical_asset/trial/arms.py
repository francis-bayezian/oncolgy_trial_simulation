"""Which protocol arms an item (intervention, radiotherapy, schedule entry) applies to: one resolver for every stage.

A StudySpec item names its arms as quoted text: an arm's label ('Regimen A'), a phrase around it ('Arm 2 (twice-weekly
XYz 27 mg/m2)'), an agent ('examplinib') or a bare designator ('A') that the arm list never defines. Substring tests
mis-assign such references (a bare 'A' is inside 'Examplinib Alone'; lesson L019), so references are resolved here on
whole words, in order:

1. no reference: the item applies to every arm;
2. the reference equals an arm's label, description, canonical name or id;
3. not a designator: the arm's label is a whole-word phrase of the reference, or the reference is a whole-word phrase
   of the arm's label or description ('examplinib' names every arm whose label names examplinib);
4. a designator ('A', 'Arm 2', 'Regimen B'): the arm whose label carries it ('Regimen B: ...', 'Arm 2'), else the arm
   whose label names the same anticancer agents as the items carrying that designator (the unique best overlap,
   Jaccard >= 0.5);
5. otherwise UNRESOLVED: the reference applies to no arm and is reported, never guessed.
"""

import re

DESIGNATOR = re.compile(r"^(?:[a-z]+\s)?([a-z]|\d{1,2}|[ivx]{1,4})$")
MIN_JACCARD = 0.5


def _t(x) -> str:
    return ((x.get("text") if isinstance(x, dict) else x) or "").strip()


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").casefold())


def _phrase_in(phrase: list[str], text: list[str]) -> bool:
    n = len(phrase)
    return bool(n) and any(text[i:i + n] == phrase for i in range(len(text) - n + 1))


def designator(ref: list[str]) -> str | None:
    """'a' for ['a'] or ['arm', 'a']; None for anything longer or not a short label."""
    m = DESIGNATOR.match(" ".join(ref))
    return m.group(1) if m else None


def _agent(it: dict) -> str:
    return (it.get("canonical_agent") or _t(it.get("agent"))).replace("_", " ").casefold()


class ArmResolver:
    def __init__(self, spec: dict):
        self.arms = spec.get("arms") or []
        self.ids = [a["arm_id"] for a in self.arms]
        self.label = {a["arm_id"]: words(_t(a.get("label"))) for a in self.arms}
        self.desc = {a["arm_id"]: words(_t(a.get("description"))) for a in self.arms}
        self.texts = {a["arm_id"]: [w for w in (self.label[a["arm_id"]], self.desc[a["arm_id"]],
                                                words((a.get("canonical_arm") or "").replace("_", " ")), words(a["arm_id"])) if w]
                      for a in self.arms}
        self.anticancer = [it for it in spec.get("interventions") or [] if it.get("category") == "anticancer_drug" and _agent(it)]
        self.agents = {_agent(it) for it in self.anticancer}
        self.items = [it for key in ("interventions", "radiotherapy") for it in spec.get(key) or []]
        self.title = words(_t((spec.get("metadata") or {}).get("title")))
        self._memo: dict[str, list[str] | None] = {}
        self.donors = self._comparator_donors()

    def _comparator_donors(self) -> dict[str, list[str]]:
        """Assumption A19: an arm no anticancer item names (e.g. 'Standard of Care' while its drugs are listed under a
        letter that resolved elsewhere) is the comparator. It receives the regimen of the arms that do not contain the
        investigational agent, the agent given in the most arms (ties: the one the title names first; no unique such agent: no donor, and the arm stays
        without agents, reported by the critic)."""
        given = {k: {_agent(it) for it in self.anticancer if k in (self._arms_of_direct(it.get("arms")) or [])} for k in self.ids}
        unnamed = [k for k in self.ids if not given[k]]
        if not unnamed:
            return {}
        counts: dict[str, int] = {}
        for agents in given.values():
            for a in agents:
                counts[a] = counts.get(a, 0) + 1
        top = max(counts.values(), default=0)
        lead = [a for a, c in counts.items() if c == top]
        if len(lead) > 1:                       # a tie: the agent the protocol title names first
            pos = {a: next((i for i in range(len(self.title)) if self.title[i:i + len(words(a))] == words(a)), None) for a in lead}
            named = sorted((i, a) for a, i in pos.items() if i is not None)
            lead = [named[0][1]] if named else lead
        if len(lead) != 1 or top < 2:
            return {}
        donors = [k for k in self.ids if given[k] and lead[0] not in given[k]]
        return {k: donors for k in unnamed} if donors else {}

    def _named_agents(self, arm_id: str) -> set[str]:
        text = self.label[arm_id] + ["|"] + self.desc[arm_id]
        return {a for a in self.agents if _phrase_in(words(a), text)}

    def _by_agents(self, d: str) -> list[str] | None:
        carried = {_agent(it) for it in self.anticancer if any(designator(words(_t(r))) == d for r in it.get("arms") or [])}
        if not carried:
            return None
        score = {}
        for k in self.ids:
            named = self._named_agents(k)
            if named:
                score[k] = len(carried & named) / len(carried | named)
        best = max(score.values(), default=0.0)
        top = [k for k, v in score.items() if v == best]
        return top if best >= MIN_JACCARD and len(top) == 1 else None

    def resolve(self, ref_text: str) -> list[str] | None:
        """The arm ids one arm reference names, or None when it cannot be resolved."""
        if ref_text not in self._memo:
            self._memo[ref_text] = self._resolve(words(ref_text))
        return self._memo[ref_text]

    def _resolve(self, ref: list[str]) -> list[str] | None:
        if not ref:
            return None
        exact = [k for k in self.ids if any(t == ref for t in self.texts[k])]
        if exact:
            return exact
        d = designator(ref)
        if d is None:
            hits = [k for k in self.ids if _phrase_in(self.label[k], ref) or _phrase_in(ref, self.label[k]) or _phrase_in(ref, self.desc[k])]
            return hits or None
        if len(ref) == 2:                                   # 'arm 2', 'regimen b': the same two words in a label
            hits = [k for k in self.ids if _phrase_in(ref, self.label[k])]
        else:                                               # a bare 'b': the label's designator ('Regimen B', 'B: ...')
            hits = [k for k in self.ids if self.label[k] and (self.label[k][0] == d or (len(self.label[k]) > 1 and self.label[k][1] == d))]
        return hits or self._by_agents(d)

    def _arms_of_direct(self, refs: list) -> list[str] | None:
        texts = [_t(r) for r in refs or [] if _t(r)]
        if not texts:
            return list(self.ids)
        found = {x for r in texts for x in (self.resolve(r) or [])}
        return sorted(found) if found else None

    def arms_of(self, refs: list) -> list[str] | None:
        """The arm ids an item applies to: every arm when it names none; None when none of its references resolves.
        A comparator arm that names no agent shares its donor arms' items (A19)."""
        direct = self._arms_of_direct(refs)
        if direct is None:
            return None
        extra = {k for k, ds in getattr(self, "donors", {}).items() if any(d in direct for d in ds)}
        return sorted(set(direct) | extra)

    def applies_to(self, refs: list, arm_id: str) -> bool:
        return arm_id in (self.arms_of(refs) or [])

    def arms_of_item(self, item: dict) -> list[str] | None:
        """arms_of for a whole item: an item that names no arm but whose agent is named by exactly one arm's label
        belongs to that arm (L035: in a two-tracer intra-patient study each injection is its own arm's), not to all."""
        refs = [_t(r) for r in item.get("arms") or [] if _t(r)]
        if not refs and item.get("category") in ("anticancer_drug", "other") and _agent(item) and self._one_product_per_arm():
            names = [w for w in (words(_agent(item)), words(_t(item.get("agent")))) if w]
            named = [k for k in self.ids if any(_phrase_in(n, self.label[k] + ["|"] + self.desc[k]) for n in names)]
            if len(named) == 1:
                return named
        return self.arms_of(item.get("arms"))

    def _one_product_per_arm(self) -> bool:
        """Every arm's label names its own product, and no two arms name the same one: only then does an item with no
        arm reference belong to the arm that names its agent (otherwise it applies to every arm, as stated)."""
        if len(self.ids) < 2:
            return False
        products = {_agent(it): [w for w in (words(_agent(it)), words(_t(it.get("agent")))) if w]
                    for it in self.items if it.get("category") in ("anticancer_drug", "other") and _agent(it)}
        named = [{p for p, names in products.items() if any(_phrase_in(n, self.label[k] + ["|"] + self.desc[k]) for n in names)}
                 for k in self.ids]
        return all(named) and all(not (named[i] & named[j]) for i in range(len(named)) for j in range(i + 1, len(named)))

    def item_applies_to(self, item: dict, arm_id: str) -> bool:
        return arm_id in (self.arms_of_item(item) or [])

    def unresolved(self) -> list[str]:
        return sorted({_t(r) for it in self.items for r in it.get("arms") or [] if _t(r) and self.resolve(_t(r)) is None})

    def arm_id_of_label(self, label: str) -> str | None:
        key = words(label)
        return next((k for k in self.ids if self.label[k] == key), None)
