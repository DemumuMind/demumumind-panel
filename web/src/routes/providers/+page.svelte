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
		deleteProvider,
		testProvider,
		discoverProvider,
		testProviderModel,
		fetchProviderKeys,
		addProviderKey,
		deleteProviderKey
	} from '$lib/api';
	import { showToast } from '$lib/stores';
	import { Bot, Plus, Trash2, RefreshCw, Play, ChevronDown, ChevronRight, X } from 'lucide-svelte';

	let items = $state<any[]>([]);
	let expanded = $state<Record<string, boolean>>({});
	let discoverResults = $state<Record<string, any>>({});
	let busyDiscover = $state<Record<string, boolean>>({});
	let providerKeys = $state<Record<string, any[]>>({});
	let newKeys = $state<Record<string, string>>({});

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
		try {
			const r = await discoverProvider(id);
			discoverResults[id] = r;
			showToast(`Discover: ${r.total} models imported ${r.imported}`, 'success');
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		} finally {
			busyDiscover[id] = false;
		}
	}

	async function testAll(id: string) {
		busyDiscover[id] = true;
		try {
			const r = await discoverProvider(id, true);
			discoverResults[id] = r;
			showToast(`Test: ${r.ok_count}/${r.total} ok`, r.ok_count > 0 ? 'success' : 'info');
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		} finally {
			busyDiscover[id] = false;
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
					<Button variant="ghost" size="sm" onclick={() => discover(p.id)} disabled={busyDiscover[p.id]}>
						<RefreshCw class="w-3.5 h-3.5" /> {busyDiscover[p.id] ? '…' : 'Discover'}
					</Button>
					<Button variant="ghost" size="sm" onclick={() => testAll(p.id)} disabled={busyDiscover[p.id]}>
						{busyDiscover[p.id] ? '…' : 'Test all'}
					</Button>
					<Button variant="ghost" size="sm" onclick={() => test(p.id)}><Play class="w-3.5 h-3.5" /></Button>
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
