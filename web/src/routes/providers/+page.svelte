<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import Button from '$lib/components/ui/button.svelte';
	import Input from '$lib/components/ui/input.svelte';
	import Select from '$lib/components/ui/select.svelte';
	import Badge from '$lib/components/ui/badge.svelte';
	import {
		fetchProviders,
		createProvider,
		deleteProvider,
		testProvider,
		discoverProvider,
		fetchProviderKeys,
		addProviderKey,
		deleteProviderKey
	} from '$lib/api';
	import { showToast } from '$lib/stores';

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
			showToast(`Discover: ${r.total} models, ${r.ok_count} ok, imported ${r.imported}`, r.ok_count > 0 ? 'success' : 'info');
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		} finally {
			busyDiscover[id] = false;
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

<h1 class="text-2xl font-bold mb-6">Providers</h1>

<Card class="mb-6">
	<h2 class="text-sm font-semibold mb-3">Add Provider</h2>
	<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3">
		<Input placeholder="Name" bind:value={name} />
		<Input placeholder="Base URL" bind:value={baseUrl} class="sm:col-span-2" />
		<Input type="password" placeholder="API Key (optional)" bind:value={apiKey} />
		<Select bind:value={protocol}>
			<option value="openai">openai</option>
			<option value="anthropic">anthropic</option>
			<option value="gemini">gemini</option>
		</Select>
		<label class="flex items-center gap-2 text-sm text-zinc-400">
			<input type="checkbox" bind:checked={isDefault} /> Default
		</label>
	</div>
	<Button onclick={add} disabled={busy || !name || !baseUrl} class="mt-3">Add</Button>
</Card>

<Card>
	<div class="overflow-x-auto">
	<table class="w-full text-sm min-w-[500px]">
		<thead>
			<tr class="text-left text-zinc-400 border-b border-zinc-800">
				<th class="py-2 w-8"></th>
				<th class="py-2">Name</th>
				<th>Base URL</th>
				<th>Protocol</th>
				<th>Status</th>
				<th class="text-right">Actions</th>
			</tr>
		</thead>
		<tbody>
			{#each items as p}
				<tr class="border-b border-zinc-800/50">
					<td class="py-2">
						<button onclick={() => toggle(p.id)} class="text-zinc-400 hover:text-zinc-200 text-xs">
							{expanded[p.id] ? '▼' : '▶'}
						</button>
					</td>
					<td class="py-2 font-medium cursor-pointer" onclick={() => toggle(p.id)}>{p.name}</td>
					<td class="text-zinc-400">{p.base_url}</td>
					<td>{p.protocol}</td>
					<td>
						<Badge variant={p.is_active ? 'success' : 'danger'}>{p.is_active ? 'active' : 'inactive'}</Badge>
					</td>
					<td class="text-right space-x-2 whitespace-nowrap">
						<button onclick={() => discover(p.id)} disabled={busyDiscover[p.id]} class="text-xs text-green-400 hover:text-green-300 disabled:opacity-50">
							{busyDiscover[p.id] ? '…' : 'Discover & Test'}
						</button>
						<button onclick={() => test(p.id)} class="text-xs text-indigo-400 hover:text-indigo-300">Test</button>
						<button onclick={() => remove(p.id)} class="text-xs text-red-400 hover:text-red-300">Delete</button>
					</td>
				</tr>
				{#if expanded[p.id]}
					<tr>
						<td></td>
						<td colspan="5" class="py-3">
							<div class="bg-zinc-900/50 rounded-lg p-3">
								<!-- keys pool -->
								<h3 class="text-xs font-semibold text-zinc-400 mb-2">Key pool</h3>
								<div class="flex flex-wrap gap-2 mb-2">
									{#each providerKeys[p.id] || [] as k}
										<span class="inline-flex items-center gap-2 rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300">
											{k.api_key_masked}
											<Badge variant={k.is_active ? 'success' : 'danger'}>{k.is_active ? 'on' : 'off'}</Badge>
											<span class="text-zinc-500">ok:{k.success_count} fail:{k.fail_count}</span>
											<button onclick={() => removeKey(p.id, k.id)} class="text-red-400 hover:text-red-300">✕</button>
										</span>
									{/each}
									{#if (providerKeys[p.id] || []).length === 0}
										<span class="text-xs text-zinc-600">no pool keys</span>
									{/if}
								</div>
								<div class="flex gap-2">
									<Input placeholder="Add pool API key" bind:value={newKeys[p.id]} class="max-w-sm" />
									<Button onclick={() => addKey(p.id)} disabled={!newKeys[p.id]}>+ Key</Button>
								</div>

								<!-- discover results -->
								{#if discoverResults[p.id]}
									<h3 class="text-xs font-semibold text-zinc-400 mt-3 mb-2">
										Models — {discoverResults[p.id].ok_count}/{discoverResults[p.id].total} ok
									</h3>
									<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-1 max-h-64 overflow-auto">
										{#each discoverResults[p.id].models as m}
											<div class="flex items-center gap-2 rounded bg-zinc-800/60 px-2 py-1 text-xs">
												<Badge variant={m.ok ? 'success' : 'danger'}>{m.ok ? 'ok' : 'err'}</Badge>
												<span class="text-zinc-300 truncate">{m.internal_model}</span>
												{#if m.latency_ms}
													<span class="text-zinc-500 ml-auto">{m.latency_ms}ms</span>
												{/if}
											</div>
										{/each}
									</div>
								{/if}
							</div>
						</td>
					</tr>
				{/if}
			{/each}
			{#if items.length === 0}
				<tr><td colspan="6" class="py-4 text-center text-zinc-500">No providers yet</td></tr>
			{/if}
		</tbody>
	</table>
	</div>
</Card>