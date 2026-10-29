"""AST mutation operators for one Python module, standard library only.

enumerate(source) lists the mutation sites in a fixed walk order;
mutate(source, index) re-parses, applies site ``index`` and returns the
unparsed mutant. Re-parsing keeps the walk deterministic.
"""

import ast

CMP_SWAP = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
}
BIN_SWAP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.FloorDiv, ast.FloorDiv: ast.Mult}
BOOL_SWAP = {ast.And: ast.Or, ast.Or: ast.And}
NAME_SWAP = {"max": "min", "min": "max"}


class Site:
    def __init__(self, kind, node, apply):
        self.kind = kind
        self.lineno = getattr(node, "lineno", 0)
        self.before = ast.unparse(node)
        self.apply = apply  # callable() -> mutated node text


def _in_docstring_position(node, parent, field):
    return isinstance(node, ast.Constant) and isinstance(parent, ast.Expr)


def enumerate_sites(source):
    tree = ast.parse(source)
    sites = []

    def replace_in(parent, field, idx, new):
        if idx is None:
            setattr(parent, field, new)
        else:
            getattr(parent, field)[idx] = new

    def visit(node, parent=None, field=None, idx=None):
        # Comparison operator swaps
        if isinstance(node, ast.Compare):
            for i, op in enumerate(node.ops):
                new_cls = CMP_SWAP.get(type(op))
                if new_cls is not None:

                    def apply(n=node, i=i, cls=new_cls):
                        n.ops[i] = cls()
                        return ast.unparse(n)

                    sites.append(Site("cmp", node, apply))
        # Arithmetic swaps
        if isinstance(node, (ast.BinOp, ast.AugAssign)):
            new_cls = BIN_SWAP.get(type(node.op))
            if new_cls is not None:

                def apply(n=node, cls=new_cls):
                    n.op = cls()
                    return ast.unparse(n)

                sites.append(Site("arith", node, apply))
        # and/or
        if isinstance(node, ast.BoolOp):
            new_cls = BOOL_SWAP[type(node.op)]

            def apply(n=node, cls=new_cls):
                n.op = cls()
                return ast.unparse(n)

            sites.append(Site("boolop", node, apply))
        # remove not
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):

            def apply(n=node, p=parent, f=field, i=idx):
                replace_in(p, f, i, n.operand)
                return ast.unparse(n.operand)

            sites.append(Site("drop_not", node, apply))
        # integer constants +-1, True/False
        if isinstance(node, ast.Constant) and not _in_docstring_position(node, parent, field):
            if type(node.value) is bool:

                def apply(n=node):
                    n.value = not n.value
                    return ast.unparse(n)

                sites.append(Site("bool", node, apply))
            elif type(node.value) is int:
                for delta in (1, -1):

                    def apply(n=node, d=delta):
                        n.value = n.value + d
                        return ast.unparse(n)

                    sites.append(Site("int", node, apply))
        # max <-> min
        if isinstance(node, ast.Name) and node.id in NAME_SWAP and isinstance(node.ctx, ast.Load):

            def apply(n=node):
                n.id = NAME_SWAP[n.id]
                return ast.unparse(n)

            sites.append(Site("maxmin", node, apply))
        # reverse=True -> False in sorted()/sort(); reversed(x) -> list(x)
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "reverse" and isinstance(kw.value, ast.Constant):

                    def apply(k=kw, n=node):
                        k.value.value = not k.value.value
                        return ast.unparse(n)

                    sites.append(Site("reverse_kw", node, apply))
            if isinstance(node.func, ast.Name) and node.func.id == "reversed":

                def apply(n=node):
                    n.func.id = "list"
                    return ast.unparse(n)

                sites.append(Site("reversed", node, apply))
        # break -> continue
        if isinstance(node, ast.Break):

            def apply(p=parent, f=field, i=idx, n=node):
                replace_in(p, f, i, ast.Continue())
                return "continue"

            sites.append(Site("break", node, apply))
        # negate if condition (if and elif)
        if isinstance(node, ast.If):

            def apply(n=node):
                n.test = ast.UnaryOp(op=ast.Not(), operand=n.test)
                return "if " + ast.unparse(n.test) + ":"

            sites.append(Site("negate_if", node, apply))
        # negate a comprehension's filter
        if isinstance(node, ast.comprehension):
            for i in range(len(node.ifs)):

                def apply(n=node, i=i):
                    n.ifs[i] = ast.UnaryOp(op=ast.Not(), operand=n.ifs[i])
                    return "if " + ast.unparse(n.ifs[i])

                sites.append(Site("negate_comp_if", node, apply))

        for name, value in ast.iter_fields(node):
            if isinstance(value, ast.AST):
                visit(value, node, name, None)
            elif isinstance(value, list):
                for j, item in enumerate(list(value)):
                    if isinstance(item, ast.AST):
                        visit(item, node, name, j)

    visit(tree)
    return tree, sites


def mutate(source, index):
    """Returns (mutant source text, site)."""
    tree, sites = enumerate_sites(source)
    site = sites[index]
    site.after = site.apply()
    ast.fix_missing_locations(tree)
    return ast.unparse(tree), site


if __name__ == "__main__":
    import sys

    for path in sys.argv[1:]:
        src = open(path).read()
        _, sites = enumerate_sites(src)
        from collections import Counter

        print(path, len(sites), dict(Counter(s.kind for s in sites)))
