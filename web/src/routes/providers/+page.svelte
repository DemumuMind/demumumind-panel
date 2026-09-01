<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import Button from '$lib/components/ui/button.svelte';
	import Input from '$lib/components/ui/input.svelte';
	import Select from '$lib/components/ui/select.svelte';
	import Badge from '$lib/components/ui/badge.svelte';
	import Table from '$lib/components/ui/table.svelte';
	import EmptyState from '$lib/components/ui/empty-state.svelte';
	import {
		fetchProviders,
		createProvider,
		updateProvider,
		deleteProvider,
		testProvider,
		discoverProviderStream,
		testProviderModel,
		fetchProviderKeys,
		addProviderKey,
		deleteProviderKey,
		fetchProviderTests,
		fetchProviderTest
	} from '$lib/api';
	import { showToast } from '$lib/stores';
	import { Bot, Plus, Trash2, RefreshCw, Play, ChevronDown, ChevronRight, X, Pencil, Save, History, Search } from 'lucide-svelte';

	let items = $state<any[]>([]);
	let expanded = $state<Record<string, boolean>>({});
	let discoverResults = $state<Record<string, any>>({});
	let busyDiscover = $state<Record<string, boolean>>({});
	let providerKeys = $state<Record<string, any[]>>({});
	let newKeys = $state<Record<string, string>>({});
	let progress = $state<Record<string, any>>({});

	// edit modal state
	let editingProvider = $state<any>(null);
	let editName = $state('');
	let editBaseUrl = $state('');
	let editApiKey = $state('');
	let editProtocol = $state('openai');
	let editIsDefault = $state(false);
	let editIsActive = $state(true);

	// history state
	let historyOpen = $state<Record<string, boolean>>({});
	let historyItems = $state<Record<string, any[]>>({});
	let historyTotal = $state<Record<string, number>>({});
	let historySort = $state<Record<string, string>>({});
	let historyOrder = $state<Record<string, string>>({});
	let historyKind = $state<Record<string, string>>({});
	let historyPage = $state<Record<string, number>>({});
	let historyRun = $state<Record<string, any>>({});

	let name = $state('');
	let baseUrl = $state('');
	let apiKey = $state('');
	let protocol = $state('openai');
	let isDefault = $state(false);
	let busy = $state(false);

	async function load() {
		try {
			const data = await fetchProviders(100, 0);
			items = data.items;
			for (const p of items) {
				if (newKeys[p.id] === undefined) newKeys[p.id] = '';
			}
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	async function loadKeys(id: string) {
		try {
			providerKeys[id] = await fetchProviderKeys(id);
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	onMount(load);

	async function add() {
		busy = true;
		try {
			await createProvider({ name, base_url: baseUrl, api_key: apiKey || null, protocol, is_default: isDefault });
			showToast('Provider created', 'success');
			name = baseUrl = apiKey = '';
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		} finally {
			busy = false;
		}
	}

	async function remove(id: string) {
		try {
			await deleteProvider(id);
			showToast('Deleted', 'success');
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	async function test(id: string) {
		try {
			const r = await testProvider(id);
			showToast(r.ok ? `OK: ${r.models.length} models` : r.message || 'Failed', r.ok ? 'success' : 'error');
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	async function discover(id: string) {
		busyDiscover[id] = true;
		progress[id] = { stage: 'starting', current: 0, total: 0, test: false, results: [] };
		try {
			const r = await discoverProviderStream(id, false, (ev) => {
				if (ev.event === 'stage') progress[id] = { ...progress[id], stage: ev.stage, total: ev.total ?? progress[id].total };
				else if (ev.event === 'import') progress[id] = { ...progress[id], current: ev.current, total: ev.total };
				else if (ev.event === 'error') progress[id] = { ...progress[id], stage: 'error' };
				else if (ev.event === 'test') {
					progress[id] = {
						...progress[id],
						current: ev.current,
						total: ev.total,
						results: [...progress[id].results, { model: ev.model, ok: ev.ok, category: ev.category }]
					};
				}
			});
			if (!r) throw new Error('No result from provider');
			discoverResults[id] = r;
			showToast(`Discover: ${r.total} models imported ${r.imported}`, 'success');
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		} finally {
			busyDiscover[id] = false;
			progress[id] = undefined;
		}
	}

	async function testAll(id: string) {
		busyDiscover[id] = true;
		progress[id] = { stage: 'starting', current: 0, total: 0, test: true, results: [] };
		try {
			const r = await discoverProviderStream(id, true, (ev) => {
				if (ev.event === 'stage') progress[id] = { ...progress[id], stage: ev.stage, total: ev.total ?? progress[id].total };
				else if (ev.event === 'import') progress[id] = { ...progress[id], current: ev.current, total: ev.total };
				else if (ev.event === 'error') progress[id] = { ...progress[id], stage: 'error' };
				else if (ev.event === 'test') {
					progress[id] = {
						...progress[id],
						current: ev.current,
						total: ev.total,
						results: [...progress[id].results, { model: ev.model, ok: ev.ok, category: ev.category }]
					};
				}
			});
			if (!r) throw new Error('No result from provider');
			discoverResults[id] = r;
			showToast(`Test: ${r.ok_count}/${r.total} ok`, (r.ok_count ?? 0) > 0 ? 'success' : 'info');
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		} finally {
			busyDiscover[id] = false;
			progress[id] = undefined;
		}
	}

	async function testModel(providerId: string, modelName: string) {
		try {
			const r = await testProviderModel(providerId, modelName);
			showToast(`${modelName}: ${r.ok ? 'ok' : r.error || 'failed'}`, r.ok ? 'success' : 'error');
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	function openEdit(p: any) {
		editingProvider = p;
		editName = p.name;
		editBaseUrl = p.base_url;
		editApiKey = '';
		editProtocol = p.protocol;
		editIsDefault = p.is_default;
		editIsActive = p.is_active;
	}

	function closeEdit() {
		editingProvider = null;
	}

	async function saveEdit() {
		if (!editingProvider) return;
		const data: any = {
			base_url: editBaseUrl,
			protocol: editProtocol,
			is_default: editIsDefault,
			is_active: editIsActive
		};
		if (editApiKey) data.api_key = editApiKey;
		try {
			await updateProvider(editingProvider.id, data);
			showToast('Provider updated', 'success');
			closeEdit();
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	async function toggleHistory(id: string) {
		historyOpen[id] = !historyOpen[id];
		if (historyOpen[id] && !historyItems[id]) {
			historySort[id] = historySort[id] || 'created_at';
			historyOrder[id] = historyOrder[id] || 'desc';
			historyKind[id] = historyKind[id] || '';
			historyPage[id] = historyPage[id] || 0;
			await loadHistory(id);
		}
	}

	async function loadHistory(id: string) {
		try {
			const data = await fetchProviderTests(id, {
				limit: 20,
				offset: (historyPage[id] || 0) * 20,
				sort: historySort[id] || 'created_at',
				order: historyOrder[id] || 'desc',
				kind: historyKind[id] || undefined
			});
			historyItems[id] = data.items;
			historyTotal[id] = data.total;
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	function sortHistory(id: string, col: string) {
		if (historySort[id] === col) {
			historyOrder[id] = historyOrder[id] === 'desc' ? 'asc' : 'desc';
		} else {
			historySort[id] = col;
			historyOrder[id] = 'desc';
		}
		historyPage[id] = 0;
		loadHistory(id);
	}

	function setHistoryKind(id: string, kind: string) {
		historyKind[id] = kind;
		historyPage[id] = 0;
		loadHistory(id);
	}

	function historyPageUp(id: string) {
		if (((historyPage[id] || 0) + 1) * 20 < (historyTotal[id] || 0)) {
			historyPage[id] = (historyPage[id] || 0) + 1;
			loadHistory(id);
		}
	}

	function historyPageDown(id: string) {
		if ((historyPage[id] || 0) > 0) {
			historyPage[id] = (historyPage[id] || 0) - 1;
			loadHistory(id);
		}
	}

	async function openRun(runId: string) {
		try {
			const r = await fetchProviderTest(runId);
			historyRun = { ...historyRun, [runId]: r };
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	function closeRun(runId: string) {
		const updated = { ...historyRun };
		delete updated[runId];
		historyRun = updated;
	}

	function toggle(id: string) {
		expanded[id] = !expanded[id];
		if (expanded[id] && !providerKeys[id]) loadKeys(id);
	}

	async function addKey(id: string) {
		const k = (newKeys[id] || '').trim();
		if (!k) return;
		try {
			await addProviderKey(id, k);
			newKeys[id] = '';
			await loadKeys(id);
			showToast('Key added', 'success');
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	async function removeKey(providerId: string, keyId: string) {
		try {
			await deleteProviderKey(providerId, keyId);
			await loadKeys(providerId);
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}
</script>

<div class="flex items-center gap-2 mb-6">
	<Bot class="w-5 h-5 text-(--accent)" />
	<h1 class="text-2xl font-bold text-(--text)">Providers</h1>
</div>

<Card class="mb-6">
	<h2 class="text-sm font-semibold mb-3 text-(--text)">Add Provider</h2>
	<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3">
		<Input placeholder="Name" bind:value={name} />
		<Input placeholder="Base URL" bind:value={baseUrl} class="sm:col-span-2" />
		<Input type="password" placeholder="API Key (optional)" bind:value={apiKey} />
		<Select bind:value={protocol}>
			<option value="openai">openai</option>
			<option value="anthropic">anthropic</option>
			<option value="gemini">gemini</option>
		</Select>
		<label class="flex items-center gap-2 text-sm text-(--text-muted)">
			<input type="checkbox" bind:checked={isDefault} class="accent-(--accent)" /> Default
		</label>
	</div>
	<Button onclick={add} disabled={busy || !name || !baseUrl} class="mt-3"><Plus class="w-4 h-4" /> Add</Button>
</Card>

<Card>
	<Table headers={['', 'Name', 'Base URL', 'Protocol', 'Status', 'Actions']}>
		{#each items as p}
			<tr class="border-b border-(--border)/50 hover:bg-(--bg-hover) transition-colors">
				<td class="py-2 px-3">
					<button onclick={() => toggle(p.id)} class="text-(--text-muted) hover:text-(--text) text-xs">
						{#if expanded[p.id]}
							<ChevronDown class="w-4 h-4" />
						{:else}
							<ChevronRight class="w-4 h-4" />
						{/if}
					</button>
				</td>
				<td class="py-2 px-3 font-medium text-(--text) cursor-pointer" onclick={() => toggle(p.id)}>{p.name}</td>
				<td class="py-2 px-3 text-(--text-muted)">{p.base_url}</td>
				<td class="py-2 px-3">
					<Badge variant="accent">{p.protocol}</Badge>
				</td>
				<td class="py-2 px-3">
					<Badge variant={p.is_active ? 'success' : 'danger'} dot>{p.is_active ? 'active' : 'inactive'}</Badge>
				</td>
				<td class="py-2 px-3 text-right space-x-2 whitespace-nowrap">
					<Button variant="ghost" size="sm" onclick={() => openEdit(p)}><Pencil class="w-3.5 h-3.5" /></Button>
					<Button variant="ghost" size="sm" onclick={() => discover(p.id)} disabled={busyDiscover[p.id]}>
						<RefreshCw class="w-3.5 h-3.5" /> {busyDiscover[p.id] ? '…' : 'Discover'}
					</Button>
					<Button variant="ghost" size="sm" onclick={() => testAll(p.id)} disabled={busyDiscover[p.id]}>
						{busyDiscover[p.id] ? '…' : 'Test all'}
					</Button>
					<Button variant="ghost" size="sm" onclick={() => test(p.id)}><Play class="w-3.5 h-3.5" /></Button>
					<Button variant="ghost" size="sm" onclick={() => toggleHistory(p.id)}><History class="w-3.5 h-3.5" /></Button>
					<Button variant="danger" size="sm" onclick={() => remove(p.id)}><Trash2 class="w-3.5 h-3.5" /></Button>
				</td>
			</tr>
			{#if expanded[p.id]}
				<tr class="bg-(--bg-card)">
					<td></td>
					<td colspan="5" class="py-3 px-3">
						<div class="rounded-lg bg-(--bg-elevated) border border-(--border) p-3">
							<h3 class="text-xs font-semibold text-(--text-muted) mb-2">Key pool</h3>
							<div class="flex flex-wrap gap-2 mb-2">
								{#each providerKeys[p.id] || [] as k}
									<span class="inline-flex items-center gap-2 rounded bg-(--bg-card) border border-(--border) px-2 py-0.5 text-xs text-(--text-muted)">
										{k.api_key_masked}
										<Badge variant={k.is_active ? 'success' : 'danger'}>{k.is_active ? 'on' : 'off'}</Badge>
										<span class="tabular-nums">ok:{k.success_count} fail:{k.fail_count}</span>
										<button onclick={() => removeKey(p.id, k.id)} class="text-red-400 hover:text-red-300"><X class="w-3 h-3" /></button>
									</span>
								{/each}
								{#if (providerKeys[p.id] || []).length === 0}
									<span class="text-xs text-(--text-faint)">no pool keys</span>
								{/if}
							</div>
							<div class="flex gap-2">
								<Input placeholder="Add pool API key" bind:value={newKeys[p.id]} class="max-w-sm" />
								<Button variant="secondary" size="sm" onclick={() => addKey(p.id)} disabled={!newKeys[p.id]}>+ Key</Button>
							</div>

							{#if progress[p.id]}
								<div class="mt-3 rounded-lg border border-(--accent)/30 bg-(--accent-soft) p-3">
									<h3 class="text-xs font-semibold text-(--accent-hover) mb-2 flex items-center gap-2">
										<RefreshCw class="w-3.5 h-3.5 animate-spin" />
										{progress[p.id].test ? 'Testing models…' : 'Discovering models…'}
									</h3>
									<div class="flex justify-between text-xs text-(--text-muted) mb-1">
										<span>Stage: {progress[p.id].stage}</span>
										<span class="tabular-nums">{progress[p.id].current} / {progress[p.id].total}</span>
									</div>
									<div class="h-1.5 bg-(--bg-card) rounded-full overflow-hidden mb-2">
										<div
											class="h-full bg-gradient-to-r from-(--accent) to-(--accent-2) rounded-full transition-all duration-300"
											style="width: {progress[p.id].total > 0 ? (progress[p.id].current / progress[p.id].total * 100) : 0}%"
										></div>
									</div>
									{#if progress[p.id].results.length > 0}
										<div class="flex flex-wrap gap-1 max-h-40 overflow-auto">
											{#each progress[p.id].results as res}
												<span class="inline-flex items-center gap-1 rounded bg-(--bg-card) border border-(--border) px-1.5 py-0.5 text-[11px]">
													{#if res.category === 'premium'}
														<Badge variant="warning">P</Badge>
													{:else if res.category === 'rate_limited'}
														<Badge variant="warning">R</Badge>
													{:else}
														<Badge variant={res.ok ? 'success' : 'danger'}>{res.ok ? '✓' : '✗'}</Badge>
													{/if}
													<span class="text-(--text-muted)">{res.model}</span>
												</span>
											{/each}
										</div>
									{/if}
								</div>
							{/if}

							{#if discoverResults[p.id]}
								<h3 class="text-xs font-semibold text-(--text-muted) mt-3 mb-2">
									Models — {discoverResults[p.id].total} found
								</h3>
								<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-1 max-h-64 overflow-auto">
									{#each discoverResults[p.id].models as m}
										<div class="flex items-center gap-2 rounded bg-(--bg-card) border border-(--border) px-2 py-1 text-xs" title={m.error || m.internal_model}>
											{#if m.category === 'premium'}
												<Badge variant="warning">premium</Badge>
											{:else if m.category === 'rate_limited'}
												<Badge variant="warning">r.limit</Badge>
											{:else if m.category === 'listed'}
												<Badge variant="default">listed</Badge>
											{:else}
												<Badge variant={m.ok ? 'success' : 'danger'}>{m.ok ? 'ok' : 'err'}</Badge>
											{/if}
											<span class="text-(--text-muted) truncate">{m.internal_model}</span>
											{#if m.latency_ms}
												<span class="text-(--text-faint) ml-auto tabular-nums">{m.latency_ms}ms</span>
											{:else if m.error && m.category !== 'listed'}
												<span class="text-(--text-faint) ml-auto truncate max-w-24" title={m.error}>{m.error}</span>
											{/if}
											<button onclick={() => testModel(p.id, m.internal_model)} class="ml-1 text-(--accent-hover) hover:text-(--accent)">Test</button>
										</div>
									{/each}
								</div>
							{/if}

							{#if historyOpen[p.id]}
								<div class="mt-3 rounded-lg border border-(--border) bg-(--bg-card) p-3">
									<h3 class="text-xs font-semibold text-(--text-muted) mb-2 flex items-center gap-2">
										<History class="w-3.5 h-3.5" />
										Test History
										<span class="ml-auto text-(--text-faint) tabular-nums">{historyTotal[p.id] ?? 0} runs</span>
									</h3>
									<div class="flex flex-wrap gap-2 mb-2">
										<div class="flex gap-1">
											<Button variant={!historyKind[p.id] ? 'primary' : 'secondary'} size="sm" onclick={() => setHistoryKind(p.id, '')}>All</Button>
											<Button variant={historyKind[p.id] === 'discover' ? 'primary' : 'secondary'} size="sm" onclick={() => setHistoryKind(p.id, 'discover')}>Discover</Button>
											<Button variant={historyKind[p.id] === 'test' ? 'primary' : 'secondary'} size="sm" onclick={() => setHistoryKind(p.id, 'test')}>Test</Button>
										</div>
										<div class="flex gap-1 ml-auto">
											<Button variant={historySort[p.id] === 'created_at' ? 'primary' : 'secondary'} size="sm" onclick={() => sortHistory(p.id, 'created_at')}>Date {historyOrder[p.id] === 'desc' ? '↓' : '↑'}</Button>
											<Button variant={historySort[p.id] === 'ok_count' ? 'primary' : 'secondary'} size="sm" onclick={() => sortHistory(p.id, 'ok_count')}>OK {historyOrder[p.id] === 'desc' ? '↓' : '↑'}</Button>
										</div>
									</div>
									<div class="overflow-x-auto">
										<table class="w-full text-sm">
											<thead>
												<tr class="text-left text-(--text-muted) border-b border-(--border)">
													<th class="py-2">Date</th>
													<th>Kind</th>
													<th>OK</th>
													<th>Total</th>
													<th></th>
												</tr>
											</thead>
											<tbody>
												{#each historyItems[p.id] || [] as run}
													<tr class="border-b border-(--border)/50 hover:bg-(--bg-hover)">
														<td class="py-1.5 text-(--text-muted) tabular-nums">{new Date(run.created_at).toLocaleString()}</td>
														<td><Badge variant={run.kind === 'test' ? 'accent' : 'default'}>{run.kind}</Badge></td>
														<td class="tabular-nums">{run.ok_count}</td>
														<td class="tabular-nums">{run.total}</td>
														<td class="text-right">
															<Button variant="ghost" size="sm" onclick={() => openRun(run.id)}>View</Button>
														</td>
													</tr>
													{#if historyRun[run.id]}
														<tr class="bg-(--bg-card)">
															<td colspan="5" class="py-2">
																<div class="flex justify-between items-center mb-1">
																	<span class="text-xs text-(--text-muted)">Models — {historyRun[run.id].total}</span>
																	<button onclick={() => closeRun(run.id)} class="text-(--text-faint) hover:text-(--text-muted)"><X class="w-3.5 h-3.5" /></button>
																</div>
																<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-1 max-h-48 overflow-auto">
																	{#each (historyRun[run.id].result?.models || []) as m}
																		<div class="flex items-center gap-2 rounded bg-(--bg-elevated) border border-(--border) px-2 py-1 text-xs" title={m.error || m.internal_model}>
																			{#if m.category === 'premium'}
																				<Badge variant="warning">premium</Badge>
																			{:else if m.category === 'rate_limited'}
																				<Badge variant="warning">r.limit</Badge>
																			{:else}
																				<Badge variant={m.ok ? 'success' : 'danger'}>{m.ok ? 'ok' : 'err'}</Badge>
																			{/if}
																			<span class="text-(--text-muted) truncate">{m.internal_model}</span>
																			{#if m.latency_ms}
																				<span class="text-(--text-faint) ml-auto tabular-nums">{m.latency_ms}ms</span>
																			{/if}
																		</div>
																	{/each}
																</div>
															</td>
														</tr>
													{/if}
												{/each}
												{#if (historyItems[p.id] || []).length === 0}
													<tr><td colspan="5" class="py-3 text-center text-(--text-faint)">No test runs yet</td></tr>
												{/if}
											</tbody>
										</table>
									</div>
									<div class="flex gap-2 mt-2">
										<Button variant="secondary" size="sm" onclick={() => historyPageDown(p.id)} disabled={!historyPage[p.id]}>← Prev</Button>
										<Button variant="secondary" size="sm" onclick={() => historyPageUp(p.id)} disabled={((historyPage[p.id] || 0) + 1) * 20 >= (historyTotal[p.id] || 0)}>Next →</Button>
									</div>
								</div>
							{/if}
						</div>
					</td>
				</tr>
			{/if}
		{/each}
	</Table>
	{#if items.length === 0}
		<EmptyState title="No providers yet" description="Add your first provider to start routing requests.">
			{#snippet icon()}<Bot class="w-5 h-5" />{/snippet}
		</EmptyState>
	{/if}
</Card>

{#if editingProvider}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onclick={closeEdit}>
		<Card class="w-full max-w-md" onclick={(ev: MouseEvent) => ev.stopPropagation()}>
			<h2 class="text-sm font-semibold mb-3 text-(--text)">Edit Provider — {editName}</h2>
			<div class="space-y-3">
				<div>
					<label class="text-xs text-(--text-muted) block mb-1">Name</label>
					<Input value={editName} disabled />
				</div>
				<div>
					<label class="text-xs text-(--text-muted) block mb-1">Base URL</label>
					<Input bind:value={editBaseUrl} />
				</div>
				<div>
					<label class="text-xs text-(--text-muted) block mb-1">API Key (leave empty to keep)</label>
					<Input type="password" bind:value={editApiKey} placeholder="••••••••" />
				</div>
				<div>
					<label class="text-xs text-(--text-muted) block mb-1">Protocol</label>
					<Select bind:value={editProtocol}>
						<option value="openai">openai</option>
						<option value="anthropic">anthropic</option>
						<option value="gemini">gemini</option>
					</Select>
				</div>
				<div class="flex gap-6">
					<label class="flex items-center gap-2 text-sm text-(--text-muted)">
						<input type="checkbox" bind:checked={editIsDefault} class="accent-(--accent)" /> Default
					</label>
					<label class="flex items-center gap-2 text-sm text-(--text-muted)">
						<input type="checkbox" bind:checked={editIsActive} class="accent-(--accent)" /> Active
					</label>
				</div>
			</div>
			<div class="flex gap-2 mt-4">
				<Button variant="secondary" onclick={closeEdit}>Cancel</Button>
				<Button onclick={saveEdit} disabled={!editBaseUrl}><Save class="w-4 h-4" /> Save</Button>
			</div>
		</Card>
	</div>
{/if}
