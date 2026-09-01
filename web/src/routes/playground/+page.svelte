<script lang="ts">
	import Card from '$lib/components/ui/card.svelte';
	import Button from '$lib/components/ui/button.svelte';
	import Select from '$lib/components/ui/select.svelte';
	import Input from '$lib/components/ui/input.svelte';
	import { getJSON, streamChat } from '$lib/api';
	import { panelKey, showToast } from '$lib/stores';
	import { get } from 'svelte/store';
	import { onMount } from 'svelte';

	let models = $state<any[]>([]);
	let selectedModel = $state('');
	let history = $state<{ role: string; content: string; reasoning?: string }[]>([]);
	let draft = $state('');
	let busy = $state(false);
	let temperature = $state('0.7');
	let maxTokens = $state('256');

	onMount(async () => {
		try {
			const data = await getJSON<any>('/v1/models?limit=200&offset=0');
			models = data.items || [];
			if (models.length) selectedModel = models[0].user_model_id;
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	});

	function send() {
		if (!get(panelKey)) {
			showToast('Login first', 'error');
			return;
		}
		if (!selectedModel || !draft.trim() || busy) return;
		busy = true;
		const userText = draft.trim();
		draft = '';
		const userIdx = history.length;
		history = [...history, { role: 'user', content: userText }];
		const assistantIdx = history.length;
		history = [...history, { role: 'assistant', content: '', reasoning: '' }];
		const messagesForApi = history
			.slice(0, userIdx + 1)
			.map((m) => ({ role: m.role, content: m.content }));
		const temp = parseFloat(temperature.replace(',', '.')) || 0.7;
		const maxT = parseInt(maxTokens) || undefined;
		streamIt(messagesForApi, temp, maxT, assistantIdx);
	}

	async function streamIt(messagesForApi: any[], temp: number, maxT: number | undefined, idx: number) {
		try {
			for await (const chunk of streamChat({
				model: selectedModel,
				messages: messagesForApi,
				temperature: temp,
				max_tokens: maxT
			})) {
				if (chunk.content) history[idx].content += chunk.content;
				if (chunk.reasoning) history[idx].reasoning = (history[idx].reasoning || '') + chunk.reasoning;
			}
		} catch (e: any) {
			history[idx].content = `Error: ${e.message}`;
		} finally {
			busy = false;
		}
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			send();
		}
	}
</script>

<h1 class="text-2xl font-bold mb-6">Playground</h1>

<Card class="mb-6">
	<div class="flex flex-col sm:flex-row gap-3 mb-4 items-end">
		<div class="flex-1 w-full">
			<label for="pg-model" class="text-xs text-zinc-500 block mb-1">Model</label>
			<Select id="pg-model" bind:value={selectedModel}>
				{#each models as m}
					<option value={m.user_model_id}>{m.user_model_id} ({m.provider?.name})</option>
				{/each}
			</Select>
		</div>
		<div class="w-full sm:w-24">
			<label for="pg-temp" class="text-xs text-zinc-500 block mb-1">Temp</label>
			<Input id="pg-temp" type="text" bind:value={temperature} placeholder="0.7" />
		</div>
		<div class="w-full sm:w-24">
			<label for="pg-max" class="text-xs text-zinc-500 block mb-1">Max tokens</label>
			<Input id="pg-max" type="number" bind:value={maxTokens} min="1" max="99999" step="1" />
		</div>
	</div>

	<div class="flex flex-col gap-3 mb-4 max-h-[55vh] overflow-auto">
		{#each history as msg, i}
			{#if msg.role === 'user'}
				<div class="self-end max-w-[80%] rounded-xl bg-indigo-700 px-3 py-2 text-sm text-white whitespace-pre-wrap">
					{msg.content}
				</div>
			{:else}
				<div class="self-start max-w-[85%] rounded-xl bg-zinc-800 px-3 py-2 text-sm text-zinc-100">
					{#if msg.reasoning}
						<details class="mb-1">
							<summary class="cursor-pointer text-xs text-zinc-500 select-none">Мысли</summary>
							<pre class="mt-1 whitespace-pre-wrap text-xs text-zinc-400">{msg.reasoning}</pre>
						</details>
					{/if}
					<div class="whitespace-pre-wrap">{msg.content || (busy && i === history.length - 1 ? '…' : '')}</div>
				</div>
			{/if}
		{/each}
		{#if history.length === 0}
			<p class="text-center text-zinc-600 text-sm py-6">Напиши сообщение, чтобы начать чат</p>
		{/if}
	</div>

	<div class="flex gap-2 items-end">
		<textarea
			class="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
			rows={2}
			placeholder="Сообщение… (Enter — отправить)"
			bind:value={draft}
			onkeydown={onKeydown}
		></textarea>
		<Button onclick={send} disabled={busy || !draft.trim() || !selectedModel}>
			{busy ? '…' : 'Send'}
		</Button>
	</div>
</Card>