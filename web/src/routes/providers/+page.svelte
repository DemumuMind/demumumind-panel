<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import Button from '$lib/components/ui/button.svelte';
	import Input from '$lib/components/ui/input.svelte';
	import Select from '$lib/components/ui/select.svelte';
	import Badge from '$lib/components/ui/badge.svelte';
	import { fetchProviders, createProvider, deleteProvider, testProvider } from '$lib/api';
	import { showToast } from '$lib/stores';

	let items = $state<any[]>([]);
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
				<th class="py-2">Name</th>
				<th>Base URL</th>
				<th>Protocol</th>
				<th>Status</th>
				<th>Default</th>
				<th class="text-right">Actions</th>
			</tr>
		</thead>
		<tbody>
			{#each items as p}
				<tr class="border-b border-zinc-800/50">
					<td class="py-2 font-medium">{p.name}</td>
					<td class="text-zinc-400">{p.base_url}</td>
					<td>{p.protocol}</td>
					<td>
						<Badge variant={p.is_active ? 'success' : 'danger'}>{p.is_active ? 'active' : 'inactive'}</Badge>
					</td>
					<td>{p.is_default ? '✓' : ''}</td>
					<td class="text-right space-x-2">
						<button onclick={() => test(p.id)} class="text-xs text-indigo-400 hover:text-indigo-300">Test</button>
						<button onclick={() => remove(p.id)} class="text-xs text-red-400 hover:text-red-300">Delete</button>
					</td>
				</tr>
			{/each}
			{#if items.length === 0}
				<tr><td colspan="6" class="py-4 text-center text-zinc-500">No providers yet</td></tr>
			{/if}
		</tbody>
	</table>
	</div>
</Card>