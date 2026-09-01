<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import Button from '$lib/components/ui/button.svelte';
	import Input from '$lib/components/ui/input.svelte';
	import Badge from '$lib/components/ui/badge.svelte';
	import { postJSON, fetchMcpServers, createMcpServer, deleteMcpServer, fetchMcpPermissions, createMcpPermission, deleteMcpPermission } from '$lib/api';
	import { showToast } from '$lib/stores';
	import { Cable, ShieldPlus, Trash2, Send } from 'lucide-svelte';

	let servers = $state<any[]>([]);
	let permissions = $state<any[]>([]);
	let newServerName = $state('');
	let newServerUrl = $state('');
	let newServerDesc = $state('');
	let newPermAgent = $state('');
	let newPermTool = $state('');
	let newPermBudget = $state('0');
	let serverName = $state('');
	let toolName = $state('');
	let method = $state('tools/list');
	let params = $state('{}');
	let result = $state('');
	let busy = $state(false);

	async function load() {
		try {
			const [s, p] = await Promise.all([fetchMcpServers(100, 0), fetchMcpPermissions(100, 0)]);
			servers = s.items;
			permissions = p.items;
			if (!serverName && servers.length) serverName = servers[0].name;
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}
	onMount(load);

	async function addServer() {
		if (!newServerName || !newServerUrl) return;
		try {
			await createMcpServer({ name: newServerName, base_url: newServerUrl, description: newServerDesc });
			showToast('Server added', 'success');
			newServerName = newServerUrl = newServerDesc = '';
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	async function removeServer(id: string) {
		try {
			await deleteMcpServer(id);
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	async function addPermission() {
		if (!newPermAgent || !newPermTool) return;
		try {
			await createMcpPermission({ agent_type: newPermAgent, tool_name: newPermTool, allowed: true, budget_per_day: parseFloat(newPermBudget) || 0 });
			showToast('Permission added', 'success');
			newPermAgent = newPermTool = '';
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	async function removePermission(id: string) {
		try {
			await deleteMcpPermission(id);
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	async function call() {
		result = '';
		let parsed: any;
		try {
			parsed = JSON.parse(params);
		} catch {
			showToast('Invalid JSON in params', 'error');
			return;
		}
		busy = true;
		try {
			const p = { server: serverName, tool: toolName, ...parsed };
			const r = await postJSON<any>('/mcp', { jsonrpc: '2.0', id: '1', method, params: p });
			result = JSON.stringify(r, null, 2);
		} catch (e: any) {
			result = `Error: ${e.message}`;
		} finally {
			busy = false;
		}
	}
</script>

<div class="flex items-center gap-2 mb-6">
	<Cable class="w-5 h-5 text-(--accent)" />
	<h1 class="text-2xl font-bold text-(--text)">MCP</h1>
</div>

<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
	<Card>
		<h2 class="text-sm font-semibold mb-3 text-(--text)">Servers</h2>
		<div class="space-y-1 mb-3 max-h-56 overflow-auto">
			{#each servers as s}
				<div class="flex items-center justify-between gap-2 rounded bg-(--bg-elevated) border border-(--border) px-2 py-1.5 text-xs">
					<div class="min-w-0">
						<span class="font-medium text-(--text)">{s.name}</span>
						<span class="text-(--text-faint) ml-2 truncate">{s.base_url}</span>
					</div>
					<button onclick={() => removeServer(s.id)} class="text-red-400 hover:text-red-300 shrink-0"><Trash2 class="w-3.5 h-3.5" /></button>
				</div>
			{/each}
			{#if servers.length === 0}
				<p class="text-center text-(--text-faint) text-xs py-3">No servers</p>
			{/if}
		</div>
		<div class="space-y-2">
			<Input placeholder="Name" bind:value={newServerName} />
			<Input placeholder="Base URL" bind:value={newServerUrl} />
			<Input placeholder="Description (optional)" bind:value={newServerDesc} />
			<Button variant="secondary" onclick={addServer} disabled={!newServerName || !newServerUrl} class="mt-2"><Cable class="w-4 h-4" /> Add server</Button>
		</div>
	</Card>

	<Card>
		<h2 class="text-sm font-semibold mb-3 text-(--text)">Permissions</h2>
		<div class="space-y-1 mb-3 max-h-56 overflow-auto">
			{#each permissions as perm}
				<div class="flex items-center justify-between gap-2 rounded bg-(--bg-elevated) border border-(--border) px-2 py-1.5 text-xs">
					<div>
						<span class="text-(--text)">{perm.agent_type}</span>
						<span class="text-(--text-faint)"> → {perm.tool_name}</span>
						<Badge variant={perm.allowed ? 'success' : 'danger'} dot>{perm.allowed ? 'allowed' : 'denied'}</Badge>
						<span class="text-(--text-faint) tabular-nums">${perm.budget_per_day}</span>
					</div>
					<button onclick={() => removePermission(perm.id)} class="text-red-400 hover:text-red-300 shrink-0"><Trash2 class="w-3.5 h-3.5" /></button>
				</div>
			{/each}
			{#if permissions.length === 0}
				<p class="text-center text-(--text-faint) text-xs py-3">No permissions</p>
			{/if}
		</div>
		<div class="flex gap-2 items-center">
			<Input placeholder="agent_type" bind:value={newPermAgent} class="flex-1" />
			<Input placeholder="tool_name" bind:value={newPermTool} class="flex-1" />
			<Input placeholder="budget" bind:value={newPermBudget} class="w-20" />
		</div>
		<Button variant="secondary" onclick={addPermission} disabled={!newPermAgent || !newPermTool} class="mt-2"><ShieldPlus class="w-4 h-4" /> Add permission</Button>
	</Card>
</div>

<Card class="mb-6">
	<div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
		<div>
			<label for="mcp-server" class="text-xs text-(--text-muted) block mb-1">Server</label>
			<select id="mcp-server" class="w-full rounded-lg border border-(--border) bg-(--bg-elevated) px-3 py-2 text-sm text-(--text)" bind:value={serverName}>
				{#each servers as s}
					<option value={s.name}>{s.name}</option>
				{/each}
			</select>
		</div>
		<Input placeholder="Tool name (for tools/call)" bind:value={toolName} />
		<select class="rounded-lg border border-(--border) bg-(--bg-elevated) px-3 py-2 text-sm text-(--text)" bind:value={method}>
			<option value="initialize">initialize</option>
			<option value="tools/list">tools/list</option>
			<option value="tools/call">tools/call</option>
		</select>
	</div>
	<label for="mcp-params" class="text-xs text-(--text-muted) block mb-1">Params (JSON)</label>
	<textarea
		id="mcp-params"
		class="w-full rounded-lg border border-(--border) bg-(--bg-elevated) px-3 py-2 text-sm text-(--text) placeholder:text-(--text-faint) focus:outline-none focus:ring-2 focus:ring-(--accent)/40 focus:border-(--accent) mb-3"
		rows={4}
		bind:value={params}
	></textarea>
	<Button onclick={call} disabled={busy || !serverName}><Send class="w-4 h-4" /> {busy ? '…' : 'Send'}</Button>
</Card>

{#if result}
	<Card>
		<h2 class="text-sm font-semibold mb-2 text-(--text)">Response</h2>
		<pre class="text-xs text-(--text-muted) overflow-auto max-h-96 whitespace-pre-wrap">{result}</pre>
	</Card>
{/if}
