import assert from 'node:assert/strict';

// Models immutable commits and an atomic branch update independently of the client.
export function fakeRepository(initialIndex, initialFiles = {}) {
  let serial = 1;
  const sha = () => (serial++).toString(16).padStart(40, '0');
  const initial = sha(), commits = new Map(), trees = new Map(), requests = [];
  const initialTree = sha();
  trees.set(initialTree, { 'data/index.json': structuredClone(initialIndex), ...structuredClone(initialFiles) });
  commits.set(initial, initialTree);
  const repo = { head: initial, requests, denyWrites: false, race: false, losePatchResponse: false, corruptRead: false,
    files() { return structuredClone(trees.get(commits.get(repo.head))); },
    advance(mutator) {
      const tree = sha(), commit = sha(), files = repo.files(); mutator(files);
      trees.set(tree, files); commits.set(commit, tree); repo.head = commit;
    },
    async fetch(url, options = {}) {
      const parsed = new URL(url), method = options.method || 'GET';
      assert.equal(parsed.origin, 'https://api.github.com');
      assert.ok(parsed.pathname.startsWith('/repos/PoeticEcho/whoga/'));
      const path = parsed.pathname.slice('/repos/PoeticEcho/whoga'.length), body = options.body && JSON.parse(options.body);
      requests.push({ path, method, body, authorization: options.headers?.Authorization });
      if (method !== 'GET') assert.equal(options.headers.Authorization, 'Bearer test-token');
      const response = (data, status = 200) => ({ ok: status < 400, status, json: async () => structuredClone(data) });
      if (repo.denyWrites && method !== 'GET') return response({}, 403);
      if (path === '/git/ref/heads/main') return response({ object: { sha: repo.head } });
      if (path.startsWith('/contents/data/')) {
        const ref = parsed.searchParams.get('ref'), files = trees.get(commits.get(ref));
        const name = decodeURIComponent(path.slice('/contents/'.length));
        const file = files?.[name];
        if (!file) return response({}, 404);
        const out = structuredClone(file);
        if (repo.corruptRead && name.includes('_manual_')) out.items[0].minPrice += .1;
        return response(out);
      }
      if (path.startsWith('/git/commits/') && method === 'GET') return response({ tree: { sha: commits.get(path.split('/').at(-1)) } });
      if (path === '/git/trees' && method === 'POST') {
        assert.ok(trees.has(body.base_tree));
        const files = structuredClone(trees.get(body.base_tree));
        for (const entry of body.tree) files[entry.path] = JSON.parse(entry.content);
        const id = sha(); trees.set(id, files); return response({ sha: id }, 201);
      }
      if (path === '/git/commits' && method === 'POST') {
        const id = sha(); commits.set(id, body.tree);
        repo.lastParent = body.parents[0]; return response({ sha: id }, 201);
      }
      if (path === '/git/refs/heads/main' && method === 'PATCH') {
        assert.equal(body.force, false);
        if (repo.race) {
          repo.race = false;
          repo.advance(files => files['data/index.json'].snapshots.push({ id: '2026-10-18_other', file: '2026-10-18_other.json', date: '2026-10-18', complete: true }));
          return response({}, 422);
        }
        if (repo.lastParent !== repo.head) return response({}, 422);
        repo.head = body.sha;
        if (repo.losePatchResponse) { repo.losePatchResponse = false; throw new TypeError('lost response'); }
        return response({ object: { sha: repo.head } });
      }
      throw new Error(`Unexpected mock route: ${method} ${path}`);
    },
  };
  return repo;
}
